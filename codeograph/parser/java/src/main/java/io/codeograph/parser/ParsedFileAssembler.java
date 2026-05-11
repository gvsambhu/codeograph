package io.codeograph.parser;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Assembles the intermediate JSON envelope for a single .java compilation unit.
 *
 * <p>
 * Dispatches to per-type builders (class, interface, enum, record, annotation),
 * extracts fields and methods, wires in complexity metrics from
 * {@link ComplexityCalculator} and cohesion from {@link Lcom4Calculator}, and
 * runs the {@link LombokSynthesizer} pass before method extraction.
 *
 * <p>
 * The output envelope is the intermediate format consumed by the Python graph
 * builder. It is NOT the final graph.schema.json format.
 */
final class ParsedFileAssembler {

	private ParsedFileAssembler() {
	}

	// -------------------------------------------------------------------------
	// Envelope builder — top-level dispatch by type declaration
	// -------------------------------------------------------------------------

	/**
	 * Build the intermediate JSON envelope for one compilation unit.
	 *
	 * A .java file may technically contain multiple type declarations but in
	 * practice exactly one public type exists per file (Java convention). We
	 * process the first type declaration found.
	 */
	static JSONObject buildEnvelope(CompilationUnit cu, String sourceFile) {
		TypeDeclaration<?> type = cu.getPrimaryType()
				.orElseGet(() -> cu.getTypes().isEmpty() ? null : cu.getTypes().get(0));

		if (type == null) {
			throw new IllegalStateException("No type declaration found in: " + sourceFile);
		}

		if (type instanceof ClassOrInterfaceDeclaration decl) {
			return decl.isInterface() ? buildInterface(decl, cu, sourceFile) : buildClass(decl, cu, sourceFile);
		} else if (type instanceof EnumDeclaration decl) {
			return buildEnum(decl, cu, sourceFile);
		} else if (type instanceof RecordDeclaration decl) {
			return buildRecord(decl, cu, sourceFile);
		} else if (type instanceof AnnotationDeclaration decl) {
			return buildAnnotationType(decl, cu, sourceFile);
		}

		throw new IllegalStateException("Unrecognised type declaration: " + type.getClass().getSimpleName());
	}

	// -------------------------------------------------------------------------
	// Per-type builders
	// -------------------------------------------------------------------------

	/**
	 * Build envelope for a class declaration.
	 *
	 * Required fields (graph.schema.json ClassNode): id, kind, name, modifiers,
	 * source_file, line_range, extraction_mode
	 *
	 * Optional but important: stereotype, annotations, superclass, implements,
	 * is_inner_class, table_name, entry_point, wmc, cbo, lcom4
	 *
	 * Plus intermediate-only fields Python needs to build edges: imports, fields
	 * (with injection metadata), methods (with call list)
	 */
	private static JSONObject buildClass(ClassOrInterfaceDeclaration decl, CompilationUnit cu, String sourceFile) {

		// Lombok synthesis pass: inject synthesised methods into the AST before
		// buildMethods runs so they appear in the graph like real methods.
		LombokSynthesizer.synthesize(decl);

		JSONObject obj = new JSONObject();

		// 1. Identity
		String simpleName = decl.getNameAsString();
		String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
		String fqcn = decl.getFullyQualifiedName()
				.orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

		obj.put("kind", "class");
		obj.put("id", fqcn);
		obj.put("name", simpleName);
		obj.put("source_file", sourceFile);

		// 2. Modifiers
		obj.put("modifiers", extractModifiers(decl.getModifiers()));

		// 3. Line range
		JSONArray lineRange = decl.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
				.orElse(new JSONArray().put(0).put(0));
		obj.put("line_range", lineRange);

		// 4. Extraction mode — always "ast" from this runner
		obj.put("extraction_mode", "ast");

		// 5. Annotations — simple names, no "@" prefix
		JSONArray annotations = extractAnnotationNames(decl.getAnnotations());
		obj.put("annotations", annotations);

		List<String> annotationList = toList(annotations);

		// 6. Stereotype — first match wins
		String stereotype = annotationList.stream().filter(ParserConstants.STEREOTYPES::contains).findFirst()
				.orElse(null);
		obj.put("stereotype", stereotype != null ? stereotype : JSONObject.NULL);

		// 7. Superclass (simple name — FQCN resolution requires symbol solver, out of
		// v1)
		String superclass = decl.getExtendedTypes().isEmpty() ? null : decl.getExtendedTypes().get(0).getNameAsString();
		obj.put("superclass", superclass != null ? superclass : JSONObject.NULL);

		// 8. Implemented interfaces (simple names)
		JSONArray implemented = new JSONArray();
		decl.getImplementedTypes().forEach(t -> implemented.put(t.getNameAsString()));
		obj.put("implements", implemented);

		// 9. Inner class flag
		obj.put("is_inner_class", decl.isInnerClass());

		// 10. Table name — @Entity classes only
		String tableName = null;
		if (annotationList.contains("Entity")) {
			for (AnnotationExpr ann : decl.getAnnotations()) {
				if (!"Table".equals(ann.getNameAsString())) {
					continue;
				}
				if (ann.isNormalAnnotationExpr()) {
					for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
						if ("name".equals(pair.getNameAsString())) {
							tableName = pair.getValue().toString().replaceAll("^\"|\"$", "");
							break;
						}
					}
				} else if (ann.isSingleMemberAnnotationExpr()) {
					tableName = ann.asSingleMemberAnnotationExpr().getMemberValue().toString().replaceAll("^\"|\"$",
							"");
				}
				if (tableName != null)
					break;
			}
			if (tableName == null) {
				tableName = simpleName.toLowerCase();
			}
		}
		obj.put("table_name", tableName != null ? tableName : JSONObject.NULL);

		// 11. Entry point
		obj.put("entry_point", annotationList.contains("SpringBootApplication"));

		// 12. Imports (intermediate-only — Python converts to DependsOnEdge)
		obj.put("imports", extractImports(cu));

		// 13. Fields
		obj.put("fields", buildFields(decl, fqcn));

		// 14. Methods — build first so WMC can sum cyclomatic values
		JSONArray methodsArr = buildMethods(decl, fqcn);
		obj.put("methods", methodsArr);

		// 15. Class-level complexity metrics
		// WMC = sum of method cyclomatic complexities. C&K (1994) IEEE TSE 20(6).
		int wmc = 0;
		for (int i = 0; i < methodsArr.length(); i++) {
			Object cc = methodsArr.getJSONObject(i).get("cyclomatic_complexity");
			if (cc instanceof Integer ccInt)
				wmc += ccInt;
		}
		obj.put("wmc", wmc);

		// CBO = distinct non-trivial type references. C&K (1994) IEEE TSE 20(6).
		obj.put("cbo", ComplexityCalculator.computeCbo(decl));

		// LCOM4 = weakly connected components in method-field access graph.
		// Hitz & Montazeri (1995). Reads accessed_fields from the finished methodsArr.
		obj.put("lcom4", Lcom4Calculator.computeLcom4(methodsArr));

		return obj;
	}

	private static JSONObject buildInterface(ClassOrInterfaceDeclaration decl, CompilationUnit cu, String sourceFile) {

		JSONObject obj = new JSONObject();

		String simpleName = decl.getNameAsString();
		String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
		String fqcn = decl.getFullyQualifiedName()
				.orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

		obj.put("kind", "interface");
		obj.put("id", fqcn);
		obj.put("name", simpleName);
		obj.put("source_file", sourceFile);

		obj.put("modifiers", extractModifiers(decl.getModifiers()));

		JSONArray lineRange = decl.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
				.orElse(new JSONArray().put(0).put(0));
		obj.put("line_range", lineRange);

		obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

		JSONArray extendedInterfaces = new JSONArray();
		decl.getExtendedTypes().forEach(t -> extendedInterfaces.put(t.getNameAsString()));
		obj.put("extends_interfaces", extendedInterfaces);

		obj.put("imports", extractImports(cu));
		obj.put("methods", buildMethods(decl, fqcn));

		return obj;
	}

	private static JSONObject buildEnum(EnumDeclaration decl, CompilationUnit cu, String sourceFile) {

		JSONObject obj = new JSONObject();

		String simpleName = decl.getNameAsString();
		String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
		String fqcn = decl.getFullyQualifiedName()
				.orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

		obj.put("kind", "enum");
		obj.put("id", fqcn);
		obj.put("name", simpleName);
		obj.put("source_file", sourceFile);

		obj.put("modifiers", extractModifiers(decl.getModifiers()));

		JSONArray lineRange = decl.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
				.orElse(new JSONArray().put(0).put(0));
		obj.put("line_range", lineRange);

		obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

		JSONArray constants = new JSONArray();
		decl.getEntries().forEach(entry -> constants.put(entry.getNameAsString()));
		obj.put("constants", constants);

		JSONArray implemented = new JSONArray();
		decl.getImplementedTypes().forEach(t -> implemented.put(t.getNameAsString()));
		obj.put("implements", implemented);

		obj.put("imports", extractImports(cu));

		// EnumDeclaration is not a ClassOrInterfaceDeclaration;
		// buildFields/buildMethods
		// cannot accept it. Spring enums are typically constants-only; add overloads in
		// v1.1.
		obj.put("fields", new JSONArray());
		obj.put("methods", new JSONArray());

		return obj;
	}

	private static JSONObject buildRecord(RecordDeclaration decl, CompilationUnit cu, String sourceFile) {

		JSONObject obj = new JSONObject();

		String simpleName = decl.getNameAsString();
		String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
		String fqcn = decl.getFullyQualifiedName()
				.orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

		obj.put("kind", "record");
		obj.put("id", fqcn);
		obj.put("name", simpleName);
		obj.put("source_file", sourceFile);

		JSONArray lineRange = decl.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
				.orElse(new JSONArray().put(0).put(0));
		obj.put("line_range", lineRange);

		obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

		JSONArray components = new JSONArray();
		decl.getParameters().forEach(param -> {
			JSONObject component = new JSONObject();
			component.put("name", param.getNameAsString());
			component.put("type", param.getType().asString());
			components.put(component);
		});
		obj.put("components", components);

		JSONArray implemented = new JSONArray();
		decl.getImplementedTypes().forEach(t -> implemented.put(t.getNameAsString()));
		obj.put("implements", implemented);

		obj.put("imports", extractImports(cu));

		return obj;
	}

	private static JSONObject buildAnnotationType(AnnotationDeclaration decl, CompilationUnit cu, String sourceFile) {

		JSONObject obj = new JSONObject();

		String simpleName = decl.getNameAsString();
		String packageName = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
		String fqcn = decl.getFullyQualifiedName()
				.orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

		obj.put("kind", "annotation_type");
		obj.put("id", fqcn);
		obj.put("name", simpleName);
		obj.put("source_file", sourceFile);

		obj.put("modifiers", extractModifiers(decl.getModifiers()));

		JSONArray lineRange = decl.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
				.orElse(new JSONArray().put(0).put(0));
		obj.put("line_range", lineRange);

		obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

		JSONArray elements = new JSONArray();
		decl.getMembers().forEach(member -> {
			if (member instanceof AnnotationMemberDeclaration amd) {
				JSONObject element = new JSONObject();
				element.put("name", amd.getNameAsString());
				element.put("type", amd.getType().asString());
				Object defaultValue = amd.getDefaultValue().<Object>map(expr -> expr.toString())
						.orElse(JSONObject.NULL);
				element.put("default_value", defaultValue);
				elements.put(element);
			}
		});
		obj.put("elements", elements);

		obj.put("imports", extractImports(cu));

		return obj;
	}

	// -------------------------------------------------------------------------
	// Field builder
	// -------------------------------------------------------------------------

	/**
	 * Build the fields array for a class declaration.
	 *
	 * Each FieldDeclaration in JavaParser may declare multiple variables (e.g.
	 * "private int x, y;"). Emits one JSON object per variable.
	 *
	 * Required output per field (maps to FieldNode in graph.schema.json): id, name,
	 * type, modifiers, annotations, is_autowired, is_id, injection_type, qualifier,
	 * generation, column, constraints
	 */
	static JSONArray buildFields(ClassOrInterfaceDeclaration decl, String classFqcn) {
		JSONArray fields = new JSONArray();

		for (FieldDeclaration fieldDecl : decl.getFields()) {
			JSONArray fieldModifiers = extractModifiers(fieldDecl.getModifiers());
			JSONArray fieldAnnotations = extractAnnotationNames(fieldDecl.getAnnotations());
			List<String> annotationNames = toList(fieldAnnotations);

			boolean isAutowired = annotationNames.stream().anyMatch(ParserConstants.AUTOWIRE_ANNOTATIONS::contains);
			boolean isId = annotationNames.contains("Id");

			String qualifier = null;
			for (AnnotationExpr ann : fieldDecl.getAnnotations()) {
				if (!ParserConstants.QUALIFIER_ANNOTATION.equals(ann.getNameAsString())) {
					continue;
				}
				if (ann.isSingleMemberAnnotationExpr()) {
					String raw = ann.asSingleMemberAnnotationExpr().getMemberValue().toString();
					qualifier = raw.replaceAll("^\"|\"$", "");
				} else if (ann.isNormalAnnotationExpr()) {
					for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
						if ("value".equals(pair.getNameAsString())) {
							String raw = pair.getValue().toString();
							qualifier = raw.replaceAll("^\"|\"$", "");
							break;
						}
					}
				}
				if (qualifier != null)
					break;
			}

			String generation = null;
			for (AnnotationExpr ann : fieldDecl.getAnnotations()) {
				if (!"GeneratedValue".equals(ann.getNameAsString())) {
					continue;
				}
				if (ann.isNormalAnnotationExpr()) {
					for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
						if ("strategy".equals(pair.getNameAsString())) {
							generation = pair.getValue().toString();
							break;
						}
					}
				}
				if (generation != null)
					break;
			}

			JSONObject column = null;
			for (AnnotationExpr ann : fieldDecl.getAnnotations()) {
				if (!"Column".equals(ann.getNameAsString())) {
					continue;
				}
				if (ann.isNormalAnnotationExpr()) {
					column = new JSONObject();
					column.put("name", JSONObject.NULL);
					column.put("nullable", JSONObject.NULL);
					column.put("length", JSONObject.NULL);
					for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
						String key = pair.getNameAsString();
						String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
						switch (key) {
							case "name" -> column.put("name", raw);
							case "nullable" -> column.put("nullable", Boolean.parseBoolean(raw));
							case "length" -> {
								try {
									column.put("length", Integer.parseInt(raw));
								} catch (NumberFormatException ignored) {
									column.put("length", JSONObject.NULL);
								}
							}
						}
					}
				}
				if (column != null)
					break;
			}

			JSONArray constraints = new JSONArray();
			annotationNames.stream().filter(ParserConstants.CONSTRAINT_ANNOTATIONS::contains).forEach(constraints::put);

			for (VariableDeclarator var : fieldDecl.getVariables()) {
				JSONObject fieldObj = new JSONObject();

				String fieldName = var.getNameAsString();
				String fieldType = var.getType().asString();

				fieldObj.put("id", classFqcn + "." + fieldName);
				fieldObj.put("name", fieldName);
				fieldObj.put("type", fieldType);
				fieldObj.put("modifiers", fieldModifiers);
				fieldObj.put("annotations", fieldAnnotations);
				fieldObj.put("is_autowired", isAutowired);
				fieldObj.put("is_id", isId);

				// JSONObject.NULL is required — passing Java null silently drops the key in
				// org.json
				Object injectionType = isAutowired ? "field" : JSONObject.NULL;
				fieldObj.put("injection_type", injectionType);
				fieldObj.put("qualifier", qualifier != null ? qualifier : JSONObject.NULL);
				fieldObj.put("generation", generation != null ? generation : JSONObject.NULL);
				fieldObj.put("column", column != null ? column : JSONObject.NULL);
				fieldObj.put("constraints", constraints);

				fields.put(fieldObj);
			}
		}

		return fields;
	}

	// -------------------------------------------------------------------------
	// Method builder
	// -------------------------------------------------------------------------

	/**
	 * Build the methods array for a class declaration.
	 *
	 * Covers both regular {@link MethodDeclaration}s and
	 * {@link ConstructorDeclaration}s. Each entry carries complexity metrics (via
	 * {@link ComplexityCalculator}) and {@code accessed_fields} for LCOM4 (consumed
	 * by {@link Lcom4Calculator}).
	 */
	static JSONArray buildMethods(ClassOrInterfaceDeclaration decl, String classFqcn) {
		JSONArray methods = new JSONArray();
		String simpleName = decl.getNameAsString();

		// Collect declared field simple-names once — used to detect which fields each
		// method accesses. Lcom4Calculator reads accessed_fields from the finished
		// methodsArr without re-visiting the AST (Option B).
		Set<String> declaredFieldNames = new HashSet<>();
		for (FieldDeclaration fd : decl.getFields()) {
			for (VariableDeclarator vd : fd.getVariables()) {
				declaredFieldNames.add(vd.getNameAsString());
			}
		}

		// --- Regular methods ---
		for (MethodDeclaration method : decl.getMethods()) {
			JSONObject mObj = new JSONObject();

			String methodName = method.getNameAsString();
			JSONArray annotations = extractAnnotationNames(method.getAnnotations());
			List<String> annotationList = toList(annotations);

			mObj.put("id", buildMethodId(classFqcn, methodName, method.getParameters()));
			mObj.put("name", methodName);
			mObj.put("return_type", method.getTypeAsString());
			mObj.put("modifiers", extractModifiers(method.getModifiers()));
			mObj.put("annotations", annotations);
			mObj.put("is_constructor", false);

			JSONArray lineRange = method.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
					.orElse(new JSONArray().put(0).put(0));
			mObj.put("line_range", lineRange);

			mObj.put("parameters", buildParameters(method.getParameters()));

			mObj.put("is_bean_factory", annotationList.contains("Bean"));
			mObj.put("exception_handler", annotationList.contains("ExceptionHandler"));
			mObj.put("response_body", annotationList.contains("ResponseBody"));

			Object responseStatus = JSONObject.NULL;
			for (AnnotationExpr ann : method.getAnnotations()) {
				if (!"ResponseStatus".equals(ann.getNameAsString()))
					continue;
				if (ann.isNormalAnnotationExpr()) {
					for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
						String k = pair.getNameAsString();
						if ("value".equals(k) || "code".equals(k)) {
							responseStatus = pair.getValue().toString();
							break;
						}
					}
				}
				break;
			}
			mObj.put("response_status", responseStatus);

			mObj.put("http_metadata", buildHttpMetadata(annotationList, method.getAnnotations()));

			mObj.put("cyclomatic_complexity", ComplexityCalculator.computeCyclomatic(method));
			mObj.put("cognitive_complexity", ComplexityCalculator.computeCognitive(method));
			mObj.put("method_loc", ComplexityCalculator.computeMethodLoc(method));

			JSONArray calls = new JSONArray();
			method.findAll(MethodCallExpr.class).forEach(call -> calls.put(call.toString()));
			mObj.put("calls", calls);

			// accessed_fields: names of class fields read/written by this method.
			// Walks for NameExpr (bare: `balance`) and FieldAccessExpr (`this.balance`).
			JSONArray accessedFields = new JSONArray();
			Set<String> accessedFieldSet = new HashSet<>();
			for (NameExpr ne : method.findAll(NameExpr.class)) {
				String name = ne.getNameAsString();
				if (declaredFieldNames.contains(name))
					accessedFieldSet.add(name);
			}
			for (FieldAccessExpr fae : method.findAll(FieldAccessExpr.class)) {
				String name = fae.getNameAsString();
				if (declaredFieldNames.contains(name))
					accessedFieldSet.add(name);
			}
			for (String name : accessedFieldSet)
				accessedFields.put(name);
			mObj.put("accessed_fields", accessedFields);

			// is_synthesised: true for methods injected by LombokSynthesizer.
			// LombokSynthesizer marks its methods with a @SynthesisedByLombok annotation.
			boolean isSynthesised = annotationList.contains("SynthesisedByLombok");
			mObj.put("is_synthesised", isSynthesised);

			methods.put(mObj);
		}

		// --- Constructors ---
		for (ConstructorDeclaration ctor : decl.getConstructors()) {
			JSONObject mObj = new JSONObject();

			JSONArray annotations = extractAnnotationNames(ctor.getAnnotations());
			List<String> annotationList = toList(annotations);

			mObj.put("id", buildMethodId(classFqcn, simpleName, ctor.getParameters()));
			mObj.put("name", simpleName);
			mObj.put("return_type", classFqcn);
			mObj.put("modifiers", extractModifiers(ctor.getModifiers()));
			mObj.put("annotations", annotations);
			mObj.put("is_constructor", true);

			JSONArray lineRange = ctor.getRange().map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
					.orElse(new JSONArray().put(0).put(0));
			mObj.put("line_range", lineRange);

			mObj.put("parameters", buildParameters(ctor.getParameters()));

			mObj.put("is_bean_factory", false);
			mObj.put("exception_handler", false);
			mObj.put("response_body", false);
			mObj.put("response_status", JSONObject.NULL);
			mObj.put("http_metadata", JSONObject.NULL);

			mObj.put("cyclomatic_complexity", ComplexityCalculator.computeCyclomatic(ctor));
			mObj.put("cognitive_complexity", ComplexityCalculator.computeCognitive(ctor));
			mObj.put("method_loc", ComplexityCalculator.computeMethodLoc(ctor));

			JSONArray calls = new JSONArray();
			ctor.findAll(MethodCallExpr.class).forEach(call -> calls.put(call.toString()));
			mObj.put("calls", calls);

			JSONArray accessedFields = new JSONArray();
			Set<String> accessedFieldSet = new HashSet<>();
			for (NameExpr ne : ctor.findAll(NameExpr.class)) {
				String name = ne.getNameAsString();
				if (declaredFieldNames.contains(name))
					accessedFieldSet.add(name);
			}
			for (FieldAccessExpr fae : ctor.findAll(FieldAccessExpr.class)) {
				String name = fae.getNameAsString();
				if (declaredFieldNames.contains(name))
					accessedFieldSet.add(name);
			}
			for (String name : accessedFieldSet)
				accessedFields.put(name);
			mObj.put("accessed_fields", accessedFields);

			boolean isSynthesised = annotationList.contains("SynthesisedByLombok");
			mObj.put("is_synthesised", isSynthesised);

			methods.put(mObj);
		}

		return methods;
	}

	// -------------------------------------------------------------------------
	// Parameter builder
	// -------------------------------------------------------------------------

	/**
	 * Build the parameters array for one method.
	 *
	 * Each entry maps to ParameterFact in graph.schema.json: name, type, validate,
	 * constraints, binding
	 */
	private static JSONArray buildParameters(NodeList<Parameter> params) {
		JSONArray result = new JSONArray();

		for (Parameter param : params) {
			JSONObject p = new JSONObject();
			JSONArray paramAnnotations = extractAnnotationNames(param.getAnnotations());
			List<String> paramAnnotationList = toList(paramAnnotations);

			p.put("name", param.getNameAsString());
			p.put("type", param.getType().asString());

			p.put("validate", paramAnnotationList.contains("Valid") || paramAnnotationList.contains("Validated"));

			JSONArray constraints = new JSONArray();
			paramAnnotationList.stream().filter(ParserConstants.CONSTRAINT_ANNOTATIONS::contains)
					.forEach(constraints::put);
			p.put("constraints", constraints);

			p.put("binding", buildParameterBinding(paramAnnotationList, param.getAnnotations()));

			result.put(p);
		}

		return result;
	}

	/**
	 * Extract Spring parameter-binding metadata from a single parameter's
	 * annotations.
	 *
	 * Returns {@link JSONObject#NULL} when no binding annotation is present.
	 */
	private static Object buildParameterBinding(List<String> annotationNames, NodeList<AnnotationExpr> annotations) {
		String kind = null;
		String annotKey = null;

		if (annotationNames.contains("PathVariable")) {
			kind = "path";
			annotKey = "PathVariable";
		} else if (annotationNames.contains("RequestParam")) {
			kind = "query";
			annotKey = "RequestParam";
		} else if (annotationNames.contains("RequestBody")) {
			kind = "body";
			annotKey = "RequestBody";
		} else if (annotationNames.contains("RequestHeader")) {
			kind = "header";
			annotKey = "RequestHeader";
		} else if (annotationNames.contains("ModelAttribute")) {
			kind = "model_attribute";
			annotKey = "ModelAttribute";
		}

		if (kind == null)
			return JSONObject.NULL;

		JSONObject binding = new JSONObject();
		binding.put("kind", kind);
		binding.put("name", JSONObject.NULL);
		binding.put("required", true);
		binding.put("default_value", JSONObject.NULL);

		for (AnnotationExpr ann : annotations) {
			if (!annotKey.equals(ann.getNameAsString()))
				continue;

			if (ann.isSingleMemberAnnotationExpr()) {
				String raw = ann.asSingleMemberAnnotationExpr().getMemberValue().toString().replaceAll("^\"|\"$", "");
				binding.put("name", raw);
			} else if (ann.isNormalAnnotationExpr()) {
				for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
					String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
					switch (pair.getNameAsString()) {
						case "value", "name" -> binding.put("name", raw);
						case "required" -> binding.put("required", Boolean.parseBoolean(raw));
						case "defaultValue" -> binding.put("default_value", raw);
					}
				}
			}
			break;
		}

		return binding;
	}

	// -------------------------------------------------------------------------
	// HTTP metadata builder
	// -------------------------------------------------------------------------

	/**
	 * Extract HTTP mapping metadata from method-level mapping annotations.
	 *
	 * Returns {@link JSONObject#NULL} if no mapping annotation is present.
	 */
	private static Object buildHttpMetadata(List<String> annotationNames, NodeList<AnnotationExpr> annotations) {
		String httpMethod = null;
		String annotKey = null;

		if (annotationNames.contains("GetMapping")) {
			httpMethod = "GET";
			annotKey = "GetMapping";
		} else if (annotationNames.contains("PostMapping")) {
			httpMethod = "POST";
			annotKey = "PostMapping";
		} else if (annotationNames.contains("PutMapping")) {
			httpMethod = "PUT";
			annotKey = "PutMapping";
		} else if (annotationNames.contains("DeleteMapping")) {
			httpMethod = "DELETE";
			annotKey = "DeleteMapping";
		} else if (annotationNames.contains("PatchMapping")) {
			httpMethod = "PATCH";
			annotKey = "PatchMapping";
		} else if (annotationNames.contains("RequestMapping")) {
			annotKey = "RequestMapping";
		}

		if (annotKey == null)
			return JSONObject.NULL;

		String path = "";

		for (AnnotationExpr ann : annotations) {
			if (!annotKey.equals(ann.getNameAsString()))
				continue;

			if (ann.isSingleMemberAnnotationExpr()) {
				path = ann.asSingleMemberAnnotationExpr().getMemberValue().toString().replaceAll("^\"|\"$", "");
			} else if (ann.isNormalAnnotationExpr()) {
				for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
					String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
					switch (pair.getNameAsString()) {
						case "value", "path" -> path = raw;
						case "method" -> {
							String m = pair.getValue().toString();
							if (m.contains("GET"))
								httpMethod = "GET";
							else if (m.contains("POST"))
								httpMethod = "POST";
							else if (m.contains("PUT"))
								httpMethod = "PUT";
							else if (m.contains("DELETE"))
								httpMethod = "DELETE";
							else if (m.contains("PATCH"))
								httpMethod = "PATCH";
						}
					}
				}
			}
			break;
		}

		JSONObject meta = new JSONObject();
		meta.put("method", httpMethod != null ? httpMethod : JSONObject.NULL);
		meta.put("path", path);
		return meta;
	}

	// -------------------------------------------------------------------------
	// Shared extraction helpers
	// -------------------------------------------------------------------------

	private static List<String> toList(JSONArray arr) {
		List<String> list = new ArrayList<>(arr.length());
		for (int i = 0; i < arr.length(); i++) {
			list.add(arr.getString(i));
		}
		return list;
	}

	private static JSONArray extractModifiers(NodeList<Modifier> modifiers) {
		JSONArray arr = new JSONArray();
		for (Modifier m : modifiers) {
			arr.put(m.getKeyword().asString().toLowerCase());
		}
		return arr;
	}

	private static JSONArray extractAnnotationNames(NodeList<AnnotationExpr> annotations) {
		JSONArray arr = new JSONArray();
		for (AnnotationExpr ann : annotations) {
			arr.put(ann.getNameAsString());
		}
		return arr;
	}

	private static JSONArray extractImports(CompilationUnit cu) {
		JSONArray arr = new JSONArray();
		cu.getImports().forEach(imp -> arr.put(imp.getNameAsString()));
		return arr;
	}

	private static String buildMethodId(String classFqcn, String methodName, NodeList<Parameter> params) {
		String paramTypes = params.stream().map(p -> p.getType().asString()).collect(Collectors.joining(","));
		return classFqcn + "#" + methodName + "(" + paramTypes + ")";
	}
}
