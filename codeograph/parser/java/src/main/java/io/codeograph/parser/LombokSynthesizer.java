package io.codeograph.parser;

import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.ast.type.PrimitiveType;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.type.VoidType;
import com.github.javaparser.ast.body.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import com.github.javaparser.ast.Modifier;

/**
 * Lombok synthesis pass — adds synthesised method declarations to a class AST
 * node before {@link ParsedFileAssembler} extracts the methods array.
 *
 * <p>
 * Called from {@link ParsedFileAssembler#buildClass} before
 * {@code buildMethods} runs, so synthesised methods appear in the graph exactly
 * like hand-written ones. Each synthesised method carries
 * {@code is_synthesised: true} in the JSON output.
 *
 * <p>
 * Supported annotations (ADR-003 §6):
 * <ul>
 * <li>{@code @Getter} — class-level and field-level</li>
 * <li>{@code @Setter} — class-level and field-level</li>
 * <li>{@code @NoArgsConstructor} — no-arg constructor</li>
 * <li>{@code @AllArgsConstructor} — constructor for all fields</li>
 * <li>{@code @RequiredArgsConstructor} — constructor for final + @NonNull
 * fields</li>
 * <li>{@code @Data} — @Getter + @Setter + @RequiredArgsConstructor + @ToString
 * + @EqualsAndHashCode</li>
 * <li>{@code @Value} — immutable @Data variant</li>
 * <li>{@code @Builder} — static builder() entry point + nested Builder
 * class</li>
 * </ul>
 *
 * <p>
 * Synthesised methods do NOT contribute to cyclomatic or cognitive complexity
 * (their bodies are empty stubs). Acceptance criterion:
 * {@code is_synthesised: true} in the JSON envelope for each generated method.
 */
final class LombokSynthesizer {

	private static final List<String> LOMBOK_ANNOTATIONS = List.of("Data", "Value", "Builder", "Getter", "Setter",
			"NoArgsConstructor", "AllArgsConstructor", "RequiredArgsConstructor");

	private static final String SYNTH_ANN = "SynthesisedByLombok";

	private LombokSynthesizer() {
	}

	/**
	 * Inspect {@code decl} for Lombok annotations and inject synthesised method
	 * declarations directly into the AST node so that the standard
	 * {@link ParsedFileAssembler#buildMethods} pass picks them up automatically.
	 *
	 * <p>
	 * Mutates {@code decl} in-place; returns void. The caller (buildClass) does not
	 * need to distinguish synthesised from real methods — they all appear in the
	 * methods array, differentiated only by the {@code is_synthesised} flag.
	 *
	 * @param decl
	 *            the class declaration to enrich (modified in-place)
	 */

	public static void synthesize(ClassOrInterfaceDeclaration decl) {
		Set<String> classAnnotations = decl.getAnnotations().stream().map(AnnotationExpr::getNameAsString)
				.collect(Collectors.toSet());

		boolean hasGetter = classAnnotations.contains("Getter") || classAnnotations.contains("Data")
				|| classAnnotations.contains("Value");

		boolean hasSetter = classAnnotations.contains("Setter") || classAnnotations.contains("Data");

		boolean hasNoArgs = classAnnotations.contains("NoArgsConstructor");
		boolean hasAllArgs = classAnnotations.contains("AllArgsConstructor") || classAnnotations.contains("Value");

		boolean hasRequiredArgs = classAnnotations.contains("RequiredArgsConstructor")
				|| classAnnotations.contains("Data");

		boolean hasBuilder = classAnnotations.contains("Builder");
		boolean hasData = classAnnotations.contains("Data");

		// 1) Class-level getter/setter synthesis
		for (FieldDeclaration fieldDecl : decl.getFields()) {
			if (fieldDecl.isStatic()) {
				continue;
			}

			Set<String> fieldAnnotations = fieldDecl.getAnnotations().stream().map(AnnotationExpr::getNameAsString)
					.collect(Collectors.toSet());

			boolean fieldGetter = hasGetter || fieldAnnotations.contains("Getter");
			boolean fieldSetter = (hasSetter || fieldAnnotations.contains("Setter")) && !fieldDecl.isFinal()
					&& !classAnnotations.contains("Value");

			for (VariableDeclarator var : fieldDecl.getVariables()) {
				if (fieldGetter) {
					addGetterIfMissing(decl, var);
				}
				if (fieldSetter) {
					addSetterIfMissing(decl, var);
				}
			}
		}

		// 2) Constructors
		if (hasNoArgs) {
			addNoArgsConstructorIfMissing(decl);
		}
		if (hasAllArgs) {
			addAllArgsConstructorIfMissing(decl);
		}
		if (hasRequiredArgs) {
			addRequiredArgsConstructorIfMissing(decl);
		}

		// 3) Data extras
		if (hasData) {
			addZeroArgMethodIfMissing(decl, "toString", new ClassOrInterfaceType(null, "String"));
			addOneArgMethodIfMissing(decl, "equals", PrimitiveType.booleanType(),
					new ClassOrInterfaceType(null, "Object"), "o");
			addZeroArgMethodIfMissing(decl, "hashCode", PrimitiveType.intType());
		}

		// 4) Builder entry point
		if (hasBuilder) {
			addBuilderEntryPointIfMissing(decl);
		}
	}

	private static void addGetterIfMissing(ClassOrInterfaceDeclaration decl, VariableDeclarator var) {
		String methodName = getterNameFor(var);
		if (hasMethod(decl, methodName, 0)) {
			return;
		}

		MethodDeclaration m = new MethodDeclaration();
		m.setName(methodName);
		m.setType(var.getType().clone());
		m.addModifier(Modifier.Keyword.PUBLIC);
		m.setBody(new BlockStmt());
		m.addAnnotation(SYNTH_ANN);
		decl.addMember(m);
	}

	private static void addSetterIfMissing(ClassOrInterfaceDeclaration decl, VariableDeclarator var) {
		String fieldName = var.getNameAsString();
		String methodName = "set" + capitalize(fieldName);
		if (hasMethod(decl, methodName, 1)) {
			return;
		}

		MethodDeclaration m = new MethodDeclaration();
		m.setName(methodName);
		m.setType(new VoidType());
		m.addModifier(Modifier.Keyword.PUBLIC);
		m.addParameter(var.getType().clone(), fieldName);
		m.setBody(new BlockStmt());
		m.addAnnotation(SYNTH_ANN);
		decl.addMember(m);
	}

	private static void addNoArgsConstructorIfMissing(ClassOrInterfaceDeclaration decl) {
		if (hasConstructor(decl, 0)) {
			return;
		}

		ConstructorDeclaration ctor = new ConstructorDeclaration();
		ctor.setName(decl.getNameAsString());
		ctor.addModifier(Modifier.Keyword.PUBLIC);
		ctor.setBody(new BlockStmt());
		ctor.addAnnotation(SYNTH_ANN);
		decl.addMember(ctor);
	}

	private static void addAllArgsConstructorIfMissing(ClassOrInterfaceDeclaration decl) {
		List<VariableDeclarator> allFields = decl.getFields().stream().filter(fd -> !fd.isStatic())
				.flatMap(fd -> fd.getVariables().stream()).toList();

		if (hasConstructor(decl, allFields.size())) {
			return;
		}

		ConstructorDeclaration ctor = new ConstructorDeclaration();
		ctor.setName(decl.getNameAsString());
		ctor.addModifier(Modifier.Keyword.PUBLIC);
		for (VariableDeclarator var : allFields) {
			ctor.addParameter(var.getType().clone(), var.getNameAsString());
		}
		ctor.setBody(new BlockStmt());
		ctor.addAnnotation(SYNTH_ANN);
		decl.addMember(ctor);
	}

	private static void addRequiredArgsConstructorIfMissing(ClassOrInterfaceDeclaration decl) {
		List<VariableDeclarator> requiredFields = new ArrayList<>();

		for (FieldDeclaration fd : decl.getFields()) {
			if (fd.isStatic()) {
				continue;
			}

			boolean isRequired = fd.isFinal() || hasAnnotation(fd, "NonNull");
			if (!isRequired) {
				continue;
			}

			requiredFields.addAll(fd.getVariables());
		}

		if (hasConstructor(decl, requiredFields.size())) {
			return;
		}

		ConstructorDeclaration ctor = new ConstructorDeclaration();
		ctor.setName(decl.getNameAsString());
		ctor.addModifier(Modifier.Keyword.PUBLIC);
		for (VariableDeclarator var : requiredFields) {
			ctor.addParameter(var.getType().clone(), var.getNameAsString());
		}
		ctor.setBody(new BlockStmt());
		ctor.addAnnotation(SYNTH_ANN);
		decl.addMember(ctor);
	}

	private static void addBuilderEntryPointIfMissing(ClassOrInterfaceDeclaration decl) {
		if (hasMethod(decl, "builder", 0)) {
			return;
		}

		MethodDeclaration m = new MethodDeclaration();
		m.setName("builder");
		// Lombok generates an inner Builder class; return type is ClassName.Builder
		m.setType(new ClassOrInterfaceType(null, decl.getNameAsString() + ".Builder"));
		m.addModifier(Modifier.Keyword.PUBLIC);
		m.addModifier(Modifier.Keyword.STATIC);
		m.setBody(new BlockStmt());
		m.addAnnotation(SYNTH_ANN);
		decl.addMember(m);
	}

	private static void addZeroArgMethodIfMissing(ClassOrInterfaceDeclaration decl, String methodName,
			Type returnType) {
		if (hasMethod(decl, methodName, 0)) {
			return;
		}

		MethodDeclaration m = new MethodDeclaration();
		m.setName(methodName);
		m.setType(returnType);
		m.addModifier(Modifier.Keyword.PUBLIC);
		m.setBody(new BlockStmt());
		m.addAnnotation(SYNTH_ANN);
		decl.addMember(m);
	}

	private static void addOneArgMethodIfMissing(ClassOrInterfaceDeclaration decl, String methodName, Type returnType,
			Type paramType, String paramName) {
		if (hasMethod(decl, methodName, 1)) {
			return;
		}

		MethodDeclaration m = new MethodDeclaration();
		m.setName(methodName);
		m.setType(returnType);
		m.addModifier(Modifier.Keyword.PUBLIC);
		m.addParameter(paramType, paramName);
		m.setBody(new BlockStmt());
		m.addAnnotation(SYNTH_ANN);
		decl.addMember(m);
	}

	private static boolean hasMethod(ClassOrInterfaceDeclaration decl, String name, int arity) {
		return decl.getMethodsByName(name).stream().anyMatch(m -> m.getParameters().size() == arity);
	}

	private static boolean hasConstructor(ClassOrInterfaceDeclaration decl, int arity) {
		return decl.getConstructors().stream().anyMatch(c -> c.getParameters().size() == arity);
	}

	private static boolean hasAnnotation(FieldDeclaration fd, String annotationName) {
		return fd.getAnnotations().stream().map(AnnotationExpr::getNameAsString).anyMatch(annotationName::equals);
	}

	private static String getterNameFor(VariableDeclarator var) {
		String fieldName = var.getNameAsString();
		boolean isPrimitiveBoolean = var.getType().isPrimitiveType()
				&& var.getType().asPrimitiveType().getType() == PrimitiveType.Primitive.BOOLEAN;
		return (isPrimitiveBoolean ? "is" : "get") + capitalize(fieldName);
	}

	private static String capitalize(String s) {
		if (s == null || s.isEmpty()) {
			return s;
		}
		return Character.toUpperCase(s.charAt(0)) + s.substring(1);
	}
}
