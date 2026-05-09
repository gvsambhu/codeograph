package io.codeograph.parser;

import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.type.ReferenceType;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * JavaParserRunner — structural extractor for a single .java file.
 *
 * <p>Usage:
 * <pre>
 *   java -jar parser.jar &lt;absolute-path-to-file.java&gt; &lt;corpus-root&gt;
 * </pre>
 *
 * <p>Outputs one JSON envelope to stdout (UTF-8). Exits 0 on success,
 * 1 on parse failure. All errors go to stderr so stdout stays clean JSON.
 *
 * <p>The JSON envelope shape is the intermediate format consumed by the
 * Python graph builder (codeograph/parser/java_file_parser.py). It is NOT
 * the final graph.schema.json format — Python converts it to nodes + edges.
 *
 * <p>Invoked per-file by the Python pipeline (ADR-003). The Python side
 * falls back to regex extraction if this process exits non-zero.
 */
public class JavaParserRunner {

    /**
     * Spring stereotype annotation names in first-match-wins priority order
     * (ADR-003 §9 — stereotypes category). Values match the graph schema enum.
     */
    private static final List<String> STEREOTYPES = List.of(
            "Component", "Service", "Repository", "Controller", "RestController",
            "Configuration", "ControllerAdvice", "Entity", "SpringBootApplication"
    );

    /** Annotations that signal field injection (@Autowired = Spring, @Inject = JSR-330). */
    private static final List<String> AUTOWIRE_ANNOTATIONS = List.of("Autowired", "Inject");

    /** Annotation that narrows which bean to inject by name or qualifier value. */
    private static final String QUALIFIER_ANNOTATION = "Qualifier";

    /** Bean Validation (JSR-380) constraint annotations relevant for the graph schema. */
    private static final List<String> CONSTRAINT_ANNOTATIONS = List.of(
            "NotNull", "NotBlank", "NotEmpty", "Size", "Min", "Max", "Email", "Pattern"
    );

    public static void main(String[] args) {
        if (args.length < 2) {
            System.err.println("Usage: parser.jar <java-file> <corpus-root>");
            System.exit(1);
        }

        Path javaFile   = Paths.get(args[0]);
        Path corpusRoot = Paths.get(args[1]);

        // Configure parser for Java 17 source level
        ParserConfiguration config = new ParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17);
        StaticJavaParser.setConfiguration(config);

        try {
            CompilationUnit cu = StaticJavaParser.parse(javaFile.toFile());

            // Compute source_file: path relative to corpus root, forward slashes
            String sourceFile = corpusRoot
                    .relativize(javaFile)
                    .toString()
                    .replace("\\", "/");

            JSONObject envelope = buildEnvelope(cu, sourceFile);
            System.out.println(envelope.toString());
            System.exit(0);

        } catch (Exception e) {
            System.err.println("Parse failed: " + e.getMessage());
            System.exit(1);
        }
    }

    // -------------------------------------------------------------------------
    // Envelope builder — top-level dispatch by type declaration
    // -------------------------------------------------------------------------

    /**
     * Build the intermediate JSON envelope for one compilation unit.
     *
     * A .java file may technically contain multiple type declarations but
     * in practice exactly one public type exists per file (Java convention).
     * We process the first type declaration found.
     */
    private static JSONObject buildEnvelope(CompilationUnit cu, String sourceFile) {
        TypeDeclaration<?> type = cu.getPrimaryType()
                .orElseGet(() -> cu.getTypes().isEmpty() ? null : cu.getTypes().get(0));

        if (type == null) {
            throw new IllegalStateException("No type declaration found in: " + sourceFile);
        }

        if (type instanceof ClassOrInterfaceDeclaration decl) {
            return decl.isInterface()
                    ? buildInterface(decl, cu, sourceFile)
                    : buildClass(decl, cu, sourceFile);
        } else if (type instanceof EnumDeclaration decl) {
            return buildEnum(decl, cu, sourceFile);
        } else if (type instanceof RecordDeclaration decl) {
            return buildRecord(decl, cu, sourceFile);
        } else if (type instanceof AnnotationDeclaration decl) {
            return buildAnnotationType(decl, cu, sourceFile);
        }

        throw new IllegalStateException(
                "Unrecognised type declaration: " + type.getClass().getSimpleName());
    }

    // -------------------------------------------------------------------------
    // Per-type builders
    // -------------------------------------------------------------------------

    /**
     * Build envelope for a class declaration.
     *
     * Required fields (graph.schema.json ClassNode):
     *   id, kind, name, modifiers, source_file, line_range, extraction_mode
     *
     * Optional but important:
     *   stereotype, annotations, superclass, implements, is_inner_class,
     *   table_name, entry_point, wmc, cbo, lcom4
     *
     * Plus intermediate-only fields Python needs to build edges:
     *   imports, fields (with injection metadata), methods (with call list)
     */
    private static JSONObject buildClass(
            ClassOrInterfaceDeclaration decl, CompilationUnit cu, String sourceFile) {

        JSONObject obj = new JSONObject();

        // 1. Identity
        String simpleName = decl.getNameAsString();
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");
        String fqcn = decl.getFullyQualifiedName()
                .orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

        obj.put("kind", "class");
        obj.put("id", fqcn);
        obj.put("name", simpleName);
        obj.put("source_file", sourceFile);

        // 2. Modifiers
        obj.put("modifiers", extractModifiers(decl.getModifiers()));

        // 3. Line range
        JSONArray lineRange = decl.getRange()
                .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                .orElse(new JSONArray().put(0).put(0));
        obj.put("line_range", lineRange);

        // 4. Extraction mode — always "ast" from this runner
        obj.put("extraction_mode", "ast");

        // 5. Annotations — simple names, no "@" prefix
        JSONArray annotations = extractAnnotationNames(decl.getAnnotations());
        obj.put("annotations", annotations);

        // Build a plain List<String> for contains() / stream() checks below
        List<String> annotationList = toList(annotations);

        // 6. Stereotype — first match wins
        String stereotype = annotationList.stream()
                .filter(STEREOTYPES::contains)
                .findFirst()
                .orElse(null);
        obj.put("stereotype", stereotype != null ? stereotype : JSONObject.NULL);

        // 7. Superclass (simple name — FQCN resolution requires symbol solver, out of v1)
        String superclass = decl.getExtendedTypes().isEmpty()
                ? null
                : decl.getExtendedTypes().get(0).getNameAsString();
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
                    tableName = ann.asSingleMemberAnnotationExpr()
                            .getMemberValue().toString().replaceAll("^\"|\"$", "");
                }
                if (tableName != null) break;
            }
            if (tableName == null) {
                tableName = simpleName.toLowerCase(); // JPA default
            }
        }
        obj.put("table_name", tableName != null ? tableName : JSONObject.NULL);

        // 11. Entry point
        obj.put("entry_point", annotationList.contains("SpringBootApplication"));

        // 12. Imports (intermediate-only — Python converts to DependsOnEdge)
        obj.put("imports", extractImports(cu));

        // 13. Fields
        obj.put("fields", buildFields(decl, fqcn));

        // 14. Methods
        obj.put("methods", buildMethods(decl, fqcn));

        // 15. Class-level complexity metrics — null here; populated by M7
        obj.put("wmc", JSONObject.NULL);
        obj.put("cbo", JSONObject.NULL);
        obj.put("lcom4", JSONObject.NULL);

        return obj;
    }

    private static JSONObject buildInterface(
            ClassOrInterfaceDeclaration decl, CompilationUnit cu, String sourceFile) {

        JSONObject obj = new JSONObject();

        // Identity
        String simpleName = decl.getNameAsString();
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");
        String fqcn = decl.getFullyQualifiedName()
                .orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

        obj.put("kind", "interface");
        obj.put("id", fqcn);
        obj.put("name", simpleName);
        obj.put("source_file", sourceFile);

        // Modifiers
        obj.put("modifiers", extractModifiers(decl.getModifiers()));

        // Line range
        JSONArray lineRange = decl.getRange()
                .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                .orElse(new JSONArray().put(0).put(0));
        obj.put("line_range", lineRange);

        // Annotations
        obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

        // Extended interfaces (interfaces extend, not implement)
        JSONArray extendedInterfaces = new JSONArray();
        decl.getExtendedTypes().forEach(t -> extendedInterfaces.put(t.getNameAsString()));
        obj.put("extends_interfaces", extendedInterfaces);

        // Imports (intermediate-only — Python converts to DependsOnEdge)
        obj.put("imports", extractImports(cu));

        // Methods (interfaces can have default/static methods in Java 8+)
        obj.put("methods", buildMethods(decl, fqcn));

        return obj;
    }

    private static JSONObject buildEnum(
            EnumDeclaration decl, CompilationUnit cu, String sourceFile) {

        JSONObject obj = new JSONObject();

        // Identity
        String simpleName = decl.getNameAsString();
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");
        String fqcn = decl.getFullyQualifiedName()
                .orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

        obj.put("kind", "enum");
        obj.put("id", fqcn);
        obj.put("name", simpleName);
        obj.put("source_file", sourceFile);

        // Modifiers
        obj.put("modifiers", extractModifiers(decl.getModifiers()));

        // Line range
        JSONArray lineRange = decl.getRange()
                .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                .orElse(new JSONArray().put(0).put(0));
        obj.put("line_range", lineRange);

        // Annotations
        obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

        // Enum constants in declaration order
        JSONArray constants = new JSONArray();
        decl.getEntries().forEach(entry -> constants.put(entry.getNameAsString()));
        obj.put("constants", constants);

        // Implemented interfaces
        JSONArray implemented = new JSONArray();
        decl.getImplementedTypes().forEach(t -> implemented.put(t.getNameAsString()));
        obj.put("implements", implemented);

        // Imports (intermediate-only — Python converts to DependsOnEdge)
        obj.put("imports", extractImports(cu));

        // Enum fields and methods deferred — EnumDeclaration is not a
        // ClassOrInterfaceDeclaration; buildFields/buildMethods cannot accept it.
        // Spring enums are typically constants-only; add overloads in v1.1 if needed.
        obj.put("fields", new JSONArray());
        obj.put("methods", new JSONArray());

        return obj;
    }

    private static JSONObject buildRecord(
            RecordDeclaration decl, CompilationUnit cu, String sourceFile) {

        JSONObject obj = new JSONObject();

        // Identity
        String simpleName = decl.getNameAsString();
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");
        String fqcn = decl.getFullyQualifiedName()
                .orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

        obj.put("kind", "record");
        obj.put("id", fqcn);
        obj.put("name", simpleName);
        obj.put("source_file", sourceFile);

        // Line range
        JSONArray lineRange = decl.getRange()
                .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                .orElse(new JSONArray().put(0).put(0));
        obj.put("line_range", lineRange);

        // Annotations
        obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

        // Components — the record's canonical constructor parameters
        // Each maps to NameTypePair in graph.schema.json
        JSONArray components = new JSONArray();
        decl.getParameters().forEach(param -> {
            JSONObject component = new JSONObject();
            component.put("name", param.getNameAsString());
            component.put("type", param.getType().asString());
            components.put(component);
        });
        obj.put("components", components);

        // Implemented interfaces
        JSONArray implemented = new JSONArray();
        decl.getImplementedTypes().forEach(t -> implemented.put(t.getNameAsString()));
        obj.put("implements", implemented);

        // Imports (intermediate-only — Python converts to DependsOnEdge)
        obj.put("imports", extractImports(cu));

        return obj;
    }

    private static JSONObject buildAnnotationType(
            AnnotationDeclaration decl, CompilationUnit cu, String sourceFile) {

        JSONObject obj = new JSONObject();

        // Identity
        String simpleName = decl.getNameAsString();
        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");
        String fqcn = decl.getFullyQualifiedName()
                .orElse(packageName.isEmpty() ? simpleName : packageName + "." + simpleName);

        obj.put("kind", "annotation_type");
        obj.put("id", fqcn);
        obj.put("name", simpleName);
        obj.put("source_file", sourceFile);

        // Modifiers
        obj.put("modifiers", extractModifiers(decl.getModifiers()));

        // Line range
        JSONArray lineRange = decl.getRange()
                .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                .orElse(new JSONArray().put(0).put(0));
        obj.put("line_range", lineRange);

        // Annotations on the annotation type itself (e.g. @Retention, @Target)
        obj.put("annotations", extractAnnotationNames(decl.getAnnotations()));

        // Elements — annotation member declarations map to AnnotationElement
        // in graph.schema.json: {name, type, default_value}
        JSONArray elements = new JSONArray();
        decl.getMembers().forEach(member -> {
            if (member instanceof AnnotationMemberDeclaration amd) {
                JSONObject element = new JSONObject();
                element.put("name", amd.getNameAsString());
                element.put("type", amd.getType().asString());
                Object defaultValue = amd.getDefaultValue()
                        .<Object>map(expr -> expr.toString())
                        .orElse(JSONObject.NULL);
                element.put("default_value", defaultValue);
                elements.put(element);
            }
        });
        obj.put("elements", elements);

        // Imports (intermediate-only — Python converts to DependsOnEdge)
        obj.put("imports", extractImports(cu));

        return obj;
    }

    // -------------------------------------------------------------------------
    // Field builder
    // -------------------------------------------------------------------------

    /**
     * Build the fields array for a class declaration.
     *
     * Each FieldDeclaration in JavaParser may declare multiple variables
     * (e.g. "private int x, y;"). Emit one JSON object per variable.
     *
     * Required output per field (maps to FieldNode in graph.schema.json):
     *   id        = "<classFqcn>.<fieldName>"
     *   name      = variable name
     *   type      = field type as string (use variable.getType().asString())
     *   modifiers = extractModifiers(fieldDecl.getModifiers())
     *   annotations = extractAnnotationNames(fieldDecl.getAnnotations())
     *
     * Derived booleans:
     *   is_autowired = "Autowired" or "Inject" in annotations
     *   is_id        = "Id" in annotations
     *
     * Injection metadata (for AutowiresEdge):
     *   injection_type = detect from context:
     *     "field"       — @Autowired on field directly
     *     "constructor" — field is final + no @Autowired (Lombok / implicit constructor DI)
     *     "setter"      — @Autowired on a setter method (detect separately)
     *   qualifier = value from @Qualifier annotation if present, else null
     *
     * JPA metadata:
     *   generation = value from @GeneratedValue(strategy=...) or null
     *   column     = {name, nullable, length} from @Column if present
     *
     * Validation:
     *   constraints = annotation names that are Bean Validation constraints
     *                 (NotNull, Size, Email, Min, Max, NotBlank, NotEmpty, Pattern)
     */
    private static JSONArray buildFields(ClassOrInterfaceDeclaration decl, String classFqcn) {
        JSONArray fields = new JSONArray();

        for (FieldDeclaration fieldDecl : decl.getFields()) {
            // Modifiers and annotations on the FieldDeclaration
            JSONArray fieldModifiers = extractModifiers(fieldDecl.getModifiers());
            JSONArray fieldAnnotations = extractAnnotationNames(fieldDecl.getAnnotations());

            // Rebuild a List<String> view over annotations for contains() / stream() checks
            List<String> annotationNames = toList(fieldAnnotations);

            boolean isAutowired = annotationNames.stream()
                    .anyMatch(AUTOWIRE_ANNOTATIONS::contains);

            boolean isId = annotationNames.contains("Id");

            // Qualifier — extract value from @Qualifier if present
            String qualifier = null;
            for (AnnotationExpr ann : fieldDecl.getAnnotations()) {
                if (!QUALIFIER_ANNOTATION.equals(ann.getNameAsString())) {
                    continue;
                }
                if (ann.isSingleMemberAnnotationExpr()) {
                    String raw = ann.asSingleMemberAnnotationExpr()
                            .getMemberValue().toString();
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
                if (qualifier != null) break;
            }

            // JPA @GeneratedValue(strategy=...) — keep simple string for now
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
                if (generation != null) break;
            }

            // JPA @Column(...) — extract name/nullable/length attributes
            JSONObject column = null;
            for (AnnotationExpr ann : fieldDecl.getAnnotations()) {
                if (!"Column".equals(ann.getNameAsString())) {
                    continue;
                }
                if (ann.isNormalAnnotationExpr()) {
                    column = new JSONObject();
                    // Pre-fill with JSON null so every key is always present in output
                    column.put("name", JSONObject.NULL);
                    column.put("nullable", JSONObject.NULL);
                    column.put("length", JSONObject.NULL);
                    for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
                        String key = pair.getNameAsString();
                        String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
                        switch (key) {
                            case "name"     -> column.put("name", raw);
                            case "nullable" -> column.put("nullable", Boolean.parseBoolean(raw));
                            case "length"   -> {
                                try {
                                    column.put("length", Integer.parseInt(raw));
                                } catch (NumberFormatException ignored) {
                                    column.put("length", JSONObject.NULL);
                                }
                            }
                        }
                    }
                }
                if (column != null) break;
            }

            // Validation constraints: intersection with CONSTRAINT_ANNOTATIONS
            JSONArray constraints = new JSONArray();
            annotationNames.stream()
                    .filter(CONSTRAINT_ANNOTATIONS::contains)
                    .forEach(constraints::put);

            // For each variable declared in this field declaration
            for (VariableDeclarator var : fieldDecl.getVariables()) {
                JSONObject fieldObj = new JSONObject();

                String fieldName = var.getNameAsString();
                String fieldType = var.getType().asString();

                fieldObj.put("id", classFqcn + "." + fieldName);
                fieldObj.put("name", fieldName);
                fieldObj.put("type", fieldType);
                fieldObj.put("modifiers", fieldModifiers);
                fieldObj.put("annotations", fieldAnnotations);

                // Derived booleans
                fieldObj.put("is_autowired", isAutowired);
                fieldObj.put("is_id", isId);

                // Injection metadata (field-level for now; constructor/setter handled elsewhere)
                // JSONObject.NULL is required — passing Java null silently drops the key in org.json
                Object injectionType = isAutowired ? "field" : JSONObject.NULL;
                fieldObj.put("injection_type", injectionType);
                fieldObj.put("qualifier", qualifier != null ? qualifier : JSONObject.NULL);

                // JPA metadata
                fieldObj.put("generation", generation != null ? generation : JSONObject.NULL);
                fieldObj.put("column", column != null ? column : JSONObject.NULL);

                // Validation constraints
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
     * Required output per method (maps to MethodNode in graph.schema.json):
     *   id           = "<classFqcn>#<methodName>(<param-types>)"
     *                  e.g. "com.example.UserService#findById(Long)"
     *   name         = method name (or class simple name for constructors)
     *   return_type  = method.getType().asString() ("void" for void methods)
     *                  constructor return_type = classFqcn
     *   modifiers    = extractModifiers(method.getModifiers())
     *   annotations  = extractAnnotationNames(method.getAnnotations())
     *   is_constructor = false for MethodDeclaration, true for ConstructorDeclaration
     *   line_range   = [begin.line, end.line]
     *   parameters   = buildParameters(method.getParameters())
     *
     * Spring-specific booleans:
     *   is_bean_factory  = "Bean" in annotations
     *   exception_handler = "ExceptionHandler" in annotations
     *   response_body    = "ResponseBody" in annotations
     *   response_status  = integer from @ResponseStatus(value=...) or null
     *
     * HTTP metadata (for controller methods):
     *   http_metadata = buildHttpMetadata(annotations) or null
     *
     * Complexity (leave null — M7 fills these in):
     *   cyclomatic_complexity, cognitive_complexity, method_loc
     *
     * Call expressions (for CallsEdge):
     *   calls = list of raw call expression strings from the method body
     *           e.g. ["ownerRepo.findById(id)", "validator.validate(owner)"]
     *           Hint: visit MethodCallExpr nodes inside the method body
     */
    private static JSONArray buildMethods(ClassOrInterfaceDeclaration decl, String classFqcn) {
        JSONArray methods = new JSONArray();
        String simpleName = decl.getNameAsString();

        // --- Regular methods ---
        for (MethodDeclaration method : decl.getMethods()) {
            JSONObject mObj = new JSONObject();

            String methodName = method.getNameAsString();
            JSONArray annotations = extractAnnotationNames(method.getAnnotations());
            List<String> annotationList = toList(annotations);

            mObj.put("id",           buildMethodId(classFqcn, methodName, method.getParameters()));
            mObj.put("name",         methodName);
            mObj.put("return_type",  method.getTypeAsString());
            mObj.put("modifiers",    extractModifiers(method.getModifiers()));
            mObj.put("annotations",  annotations);
            mObj.put("is_constructor", false);

            JSONArray lineRange = method.getRange()
                    .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                    .orElse(new JSONArray().put(0).put(0));
            mObj.put("line_range", lineRange);

            mObj.put("parameters", buildParameters(method.getParameters()));

            // Spring-specific booleans
            mObj.put("is_bean_factory",   annotationList.contains("Bean"));
            mObj.put("exception_handler", annotationList.contains("ExceptionHandler"));
            mObj.put("response_body",     annotationList.contains("ResponseBody"));

            // @ResponseStatus(value/code = HttpStatus.XXX) — keep as string; int resolution needs symbol solver
            Object responseStatus = JSONObject.NULL;
            for (AnnotationExpr ann : method.getAnnotations()) {
                if (!"ResponseStatus".equals(ann.getNameAsString())) continue;
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

            // HTTP mapping metadata (null for non-handler methods)
            mObj.put("http_metadata", buildHttpMetadata(annotationList, method.getAnnotations()));

            // Complexity — null here; populated by M7
            mObj.put("cyclomatic_complexity", JSONObject.NULL);
            mObj.put("cognitive_complexity",  JSONObject.NULL);
            mObj.put("method_loc",            JSONObject.NULL);

            // Raw call expressions — Python uses these to build CallsEdge
            JSONArray calls = new JSONArray();
            method.findAll(MethodCallExpr.class).forEach(call -> calls.put(call.toString()));
            mObj.put("calls", calls);

            methods.put(mObj);
        }

        // --- Constructors ---
        for (ConstructorDeclaration ctor : decl.getConstructors()) {
            JSONObject mObj = new JSONObject();

            JSONArray annotations = extractAnnotationNames(ctor.getAnnotations());

            mObj.put("id",           buildMethodId(classFqcn, simpleName, ctor.getParameters()));
            mObj.put("name",         simpleName);
            mObj.put("return_type",  classFqcn);   // convention: constructor "returns" its own FQCN
            mObj.put("modifiers",    extractModifiers(ctor.getModifiers()));
            mObj.put("annotations",  annotations);
            mObj.put("is_constructor", true);

            JSONArray lineRange = ctor.getRange()
                    .map(r -> new JSONArray().put(r.begin.line).put(r.end.line))
                    .orElse(new JSONArray().put(0).put(0));
            mObj.put("line_range", lineRange);

            mObj.put("parameters", buildParameters(ctor.getParameters()));

            // Constructors never carry HTTP / Spring-handler metadata
            mObj.put("is_bean_factory",   false);
            mObj.put("exception_handler", false);
            mObj.put("response_body",     false);
            mObj.put("response_status",   JSONObject.NULL);
            mObj.put("http_metadata",     JSONObject.NULL);

            mObj.put("cyclomatic_complexity", JSONObject.NULL);
            mObj.put("cognitive_complexity",  JSONObject.NULL);
            mObj.put("method_loc",            JSONObject.NULL);

            JSONArray calls = new JSONArray();
            ctor.findAll(MethodCallExpr.class).forEach(call -> calls.put(call.toString()));
            mObj.put("calls", calls);

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
     * Each entry maps to ParameterFact in graph.schema.json:
     *   name        = param.getNameAsString()
     *   type        = param.getType().asString()
     *   validate    = "@Valid" or "@Validated" in param annotations
     *   constraints = Bean Validation annotation names on this param
     *   binding     = buildParameterBinding(param annotations) or null
     *
     * ParameterBinding (when a Spring binding annotation is present):
     *   kind          = "path"/"query"/"body"/"header"/"model_attribute"
     *   name          = explicit value from annotation, or null
     *   required      = annotation's required attribute (default true)
     *   default_value = annotation's defaultValue attribute, or null
     */
    private static JSONArray buildParameters(NodeList<Parameter> params) {
        JSONArray result = new JSONArray();

        for (Parameter param : params) {
            JSONObject p = new JSONObject();
            JSONArray paramAnnotations = extractAnnotationNames(param.getAnnotations());
            List<String> paramAnnotationList = toList(paramAnnotations);

            p.put("name", param.getNameAsString());
            p.put("type", param.getType().asString());

            // @Valid / @Validated signal that the parameter should be validated
            p.put("validate",
                    paramAnnotationList.contains("Valid") || paramAnnotationList.contains("Validated"));

            // Bean Validation constraints present directly on the parameter
            JSONArray constraints = new JSONArray();
            paramAnnotationList.stream()
                    .filter(CONSTRAINT_ANNOTATIONS::contains)
                    .forEach(constraints::put);
            p.put("constraints", constraints);

            // Spring binding annotation (@PathVariable, @RequestParam, etc.)
            p.put("binding", buildParameterBinding(paramAnnotationList, param.getAnnotations()));

            result.put(p);
        }

        return result;
    }

    /**
     * Extract Spring parameter-binding metadata from a single parameter's annotations.
     *
     * Recognised binding annotations and their schema kinds:
     *   @PathVariable  → "path"
     *   @RequestParam  → "query"
     *   @RequestBody   → "body"
     *   @RequestHeader → "header"
     *   @ModelAttribute → "model_attribute"
     *
     * Returns JSONObject.NULL when no binding annotation is present.
     */
    private static Object buildParameterBinding(List<String> annotationNames,
                                                NodeList<AnnotationExpr> annotations) {
        // Determine which binding annotation is present (first match wins)
        String kind     = null;
        String annotKey = null;

        if      (annotationNames.contains("PathVariable"))   { kind = "path";            annotKey = "PathVariable"; }
        else if (annotationNames.contains("RequestParam"))   { kind = "query";           annotKey = "RequestParam"; }
        else if (annotationNames.contains("RequestBody"))    { kind = "body";            annotKey = "RequestBody"; }
        else if (annotationNames.contains("RequestHeader"))  { kind = "header";          annotKey = "RequestHeader"; }
        else if (annotationNames.contains("ModelAttribute")) { kind = "model_attribute"; annotKey = "ModelAttribute"; }

        if (kind == null) return JSONObject.NULL;

        JSONObject binding = new JSONObject();
        binding.put("kind",          kind);
        binding.put("name",          JSONObject.NULL);   // overwritten below if explicit
        binding.put("required",      true);              // Spring default
        binding.put("default_value", JSONObject.NULL);

        for (AnnotationExpr ann : annotations) {
            if (!annotKey.equals(ann.getNameAsString())) continue;

            if (ann.isSingleMemberAnnotationExpr()) {
                // @PathVariable("userId") — single value = binding name
                String raw = ann.asSingleMemberAnnotationExpr()
                        .getMemberValue().toString().replaceAll("^\"|\"$", "");
                binding.put("name", raw);
            } else if (ann.isNormalAnnotationExpr()) {
                for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
                    String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
                    switch (pair.getNameAsString()) {
                        case "value", "name" -> binding.put("name",          raw);
                        case "required"      -> binding.put("required",      Boolean.parseBoolean(raw));
                        case "defaultValue"  -> binding.put("default_value", raw);
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
     * Mapping annotation → HTTP method:
     *   @GetMapping     → GET
     *   @PostMapping    → POST
     *   @PutMapping     → PUT
     *   @DeleteMapping  → DELETE
     *   @PatchMapping   → PATCH
     *   @RequestMapping → read from method attribute (RequestMethod.GET etc.)
     *
     * Path: first value/path attribute of the annotation, or empty string.
     *
     * Returns null (JSONObject.NULL) if no mapping annotation is present.
     */
    private static Object buildHttpMetadata(List<String> annotationNames,
                                            NodeList<AnnotationExpr> annotations) {
        // Identify which mapping annotation is present
        String httpMethod = null;   // null only for @RequestMapping until method attr is read
        String annotKey   = null;

        if      (annotationNames.contains("GetMapping"))     { httpMethod = "GET";    annotKey = "GetMapping"; }
        else if (annotationNames.contains("PostMapping"))    { httpMethod = "POST";   annotKey = "PostMapping"; }
        else if (annotationNames.contains("PutMapping"))     { httpMethod = "PUT";    annotKey = "PutMapping"; }
        else if (annotationNames.contains("DeleteMapping"))  { httpMethod = "DELETE"; annotKey = "DeleteMapping"; }
        else if (annotationNames.contains("PatchMapping"))   { httpMethod = "PATCH";  annotKey = "PatchMapping"; }
        else if (annotationNames.contains("RequestMapping")) {                        annotKey = "RequestMapping"; }

        if (annotKey == null) return JSONObject.NULL;

        String path = "";

        for (AnnotationExpr ann : annotations) {
            if (!annotKey.equals(ann.getNameAsString())) continue;

            if (ann.isSingleMemberAnnotationExpr()) {
                // @GetMapping("/owners") — single value is the path
                path = ann.asSingleMemberAnnotationExpr()
                        .getMemberValue().toString().replaceAll("^\"|\"$", "");
            } else if (ann.isNormalAnnotationExpr()) {
                for (MemberValuePair pair : ann.asNormalAnnotationExpr().getPairs()) {
                    String raw = pair.getValue().toString().replaceAll("^\"|\"$", "");
                    switch (pair.getNameAsString()) {
                        case "value", "path" -> path = raw;
                        case "method" -> {
                            // RequestMethod.GET or just GET — extract the verb
                            String m = pair.getValue().toString();
                            if      (m.contains("GET"))    httpMethod = "GET";
                            else if (m.contains("POST"))   httpMethod = "POST";
                            else if (m.contains("PUT"))    httpMethod = "PUT";
                            else if (m.contains("DELETE")) httpMethod = "DELETE";
                            else if (m.contains("PATCH"))  httpMethod = "PATCH";
                        }
                    }
                }
            }
            break;
        }

        JSONObject meta = new JSONObject();
        meta.put("method", httpMethod != null ? httpMethod : JSONObject.NULL);
        meta.put("path",   path);
        return meta;
    }

    // -------------------------------------------------------------------------
    // Shared extraction helpers
    // -------------------------------------------------------------------------

    /**
     * Convert a JSONArray of strings to a plain List&lt;String&gt; for stream / contains() use.
     * org.json's JSONArray does not implement Collection, so this bridge is needed frequently.
     */
    private static List<String> toList(JSONArray arr) {
        List<String> list = new ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) {
            list.add(arr.getString(i));
        }
        return list;
    }

    /**
     * Extract modifier names as lowercase strings.
     * e.g. Modifier.publicModifier() → "public"
     */
    private static JSONArray extractModifiers(NodeList<Modifier> modifiers) {
        JSONArray arr = new JSONArray();
        for (Modifier m : modifiers) {
            arr.put(m.getKeyword().asString().toLowerCase());
        }
        return arr;
    }

    /**
     * Extract annotation simple names, stripping the "@" prefix.
     * e.g. @Service → "Service", @GetMapping → "GetMapping"
     * Full annotation text (with attributes) is excluded — simple name only.
     */
    private static JSONArray extractAnnotationNames(NodeList<AnnotationExpr> annotations) {
        JSONArray arr = new JSONArray();
        for (AnnotationExpr ann : annotations) {
            arr.put(ann.getNameAsString());
        }
        return arr;
    }

    /**
     * Extract all import statements as fully-qualified strings.
     * e.g. "com.example.petclinic.model.Owner"
     * Asterisk imports (import com.example.*) are included as-is.
     */
    private static JSONArray extractImports(CompilationUnit cu) {
        JSONArray arr = new JSONArray();
        cu.getImports().forEach(imp -> arr.put(imp.getNameAsString()));
        return arr;
    }

    /**
     * Derive Spring stereotype from the annotation list.
     * First match wins (see ADR-003 §9 — stereotypes category).
     * Returns null if no stereotype annotation is present.
     *
     * Recognised stereotypes (short name, no @ prefix):
     *   Component, Service, Repository, Controller, RestController,
     *   Configuration, ControllerAdvice, Entity, SpringBootApplication
     */
    private static String deriveStereotype(JSONArray annotationNames) {
        // Convert to List so we can use stream(); reuse the same first-match-wins
        // logic as buildClass (annotation-list order, filtered against STEREOTYPES).
        return toList(annotationNames).stream()
                .filter(STEREOTYPES::contains)
                .findFirst()
                .orElse(null);
    }

    /**
     * Build method ID string in graph schema format.
     * Format: <classFqcn>#<methodName>(<comma-separated-param-types>)
     * e.g.   com.example.UserService#findById(Long)
     *         com.example.UserService#save(UserDTO,BindingResult)
     */
    private static String buildMethodId(String classFqcn, String methodName,
                                        NodeList<Parameter> params) {
        String paramTypes = params.stream()
                .map(p -> p.getType().asString())
                .collect(Collectors.joining(","));
        return classFqcn + "#" + methodName + "(" + paramTypes + ")";
    }

}
