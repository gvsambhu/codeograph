package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for {@link JavaParserRunner} — structural extraction and M7 complexity metrics.
 *
 * <p>Organisation follows the three test categories agreed in M6-tests milestone:
 * <ul>
 *   <li><b>Category A — Structural</b>: kind, id, name, annotations, imports,
 *       stereotype, superclass, implements, constants, components.</li>
 *   <li><b>Category B — Field / Method metadata</b>: injection flags, qualifier,
 *       JPA column, Bean Validation constraints, HTTP metadata, parameter bindings.</li>
 *   <li><b>Category C — Complexity metrics</b>: cyclomatic, cognitive, method_loc,
 *       WMC, CBO — each verified against a hand-calculated expected value.</li>
 * </ul>
 *
 * <p>All source fixtures are inline strings — no file I/O, no subprocess. Tests call
 * package-private static methods directly after parsing via {@link StaticJavaParser}.
 *
 * <p>Assertions are left as TODOs for the learner to implement after reviewing the
 * expected values.
 */
class JavaParserRunnerTest {

    // -------------------------------------------------------------------------
    // Shared parser setup
    // -------------------------------------------------------------------------

    @BeforeAll
    static void configureParser() {
        // Mirror the language level used by the production runner.
        StaticJavaParser.setConfiguration(
                new ParserConfiguration()
                        .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
    }

    // =========================================================================
    // Category A — Structural extraction
    // =========================================================================

    @Nested
    class StructuralExtractionTests {

        // --- fixture sources ---

        /** Plain service class: one stereotype annotation, one superclass, one interface. */
        private static final String SERVICE_SOURCE = """
                package com.example;
                import com.example.repo.OwnerRepository;
                import org.springframework.stereotype.Service;
                @Service
                public class OwnerService extends BaseService implements Auditable {
                    private OwnerRepository ownerRepo;
                }
                """;

        /** Interface with two extended interfaces. */
        private static final String INTERFACE_SOURCE = """
                package com.example;
                public interface Auditable extends Serializable, Cloneable {
                    void audit();
                }
                """;

        /** Enum with three constants, one implemented interface. */
        private static final String ENUM_SOURCE = """
                package com.example;
                public enum Status implements Displayable {
                    ACTIVE, INACTIVE, PENDING;
                }
                """;

        /** Java record with two components. */
        private static final String RECORD_SOURCE = """
                package com.example;
                public record PageRequest(int page, int size) {}
                """;

        /** Annotation type with two elements, one with a default value. */
        private static final String ANNOTATION_TYPE_SOURCE = """
                package com.example;
                import java.lang.annotation.*;
                @Retention(RetentionPolicy.RUNTIME)
                @Target(ElementType.TYPE)
                public @interface Versioned {
                    int value();
                    String label() default "v1";
                }
                """;

        // --- tests ---

        @Test
        void class_kind_id_name() {
            JSONObject env = parse(SERVICE_SOURCE);
            // TODO: assertEquals("class", env.getString("kind"));
            // TODO: assertEquals("com.example.OwnerService", env.getString("id"));
            // TODO: assertEquals("OwnerService", env.getString("name"));
            // TODO: assertEquals("ast", env.getString("extraction_mode"));
        }

        @Test
        void class_stereotype_and_annotation() {
            JSONObject env = parse(SERVICE_SOURCE);
            // TODO: assertEquals("Service", env.getString("stereotype"));
            // TODO: assertTrue(toList(env.getJSONArray("annotations")).contains("Service"));
        }

        @Test
        void class_superclass_and_implements() {
            JSONObject env = parse(SERVICE_SOURCE);
            // TODO: assertEquals("BaseService", env.getString("superclass"));
            // TODO: assertEquals(1, env.getJSONArray("implements").length());
            // TODO: assertEquals("Auditable", env.getJSONArray("implements").getString(0));
        }

        @Test
        void class_imports() {
            JSONObject env = parse(SERVICE_SOURCE);
            // TODO: List<String> imports = toList(env.getJSONArray("imports"));
            // TODO: assertTrue(imports.contains("com.example.repo.OwnerRepository"));
            // TODO: assertTrue(imports.contains("org.springframework.stereotype.Service"));
        }

        @Test
        void interface_kind_and_extends() {
            JSONObject env = parse(INTERFACE_SOURCE);
            // TODO: assertEquals("interface", env.getString("kind"));
            // TODO: assertEquals(2, env.getJSONArray("extends_interfaces").length());
        }

        @Test
        void enum_kind_and_constants() {
            JSONObject env = parse(ENUM_SOURCE);
            // TODO: assertEquals("enum", env.getString("kind"));
            // TODO: assertEquals(3, env.getJSONArray("constants").length());
            // TODO: assertEquals("ACTIVE", env.getJSONArray("constants").getString(0));
        }

        @Test
        void enum_implements() {
            JSONObject env = parse(ENUM_SOURCE);
            // TODO: assertEquals(1, env.getJSONArray("implements").length());
            // TODO: assertEquals("Displayable", env.getJSONArray("implements").getString(0));
        }

        @Test
        void record_kind_and_components() {
            JSONObject env = parse(RECORD_SOURCE);
            // TODO: assertEquals("record", env.getString("kind"));
            // TODO: assertEquals(2, env.getJSONArray("components").length());
            // TODO: assertEquals("page", env.getJSONArray("components").getJSONObject(0).getString("name"));
            // TODO: assertEquals("int",  env.getJSONArray("components").getJSONObject(0).getString("type"));
        }

        @Test
        void annotation_type_kind_and_elements() {
            JSONObject env = parse(ANNOTATION_TYPE_SOURCE);
            // TODO: assertEquals("annotation_type", env.getString("kind"));
            // TODO: assertEquals(2, env.getJSONArray("elements").length());
            // first element: value(), no default
            // TODO: JSONObject elem0 = env.getJSONArray("elements").getJSONObject(0);
            // TODO: assertEquals("value", elem0.getString("name"));
            // TODO: assertEquals("int",   elem0.getString("type"));
            // TODO: assertTrue(elem0.isNull("default_value"));
            // second element: label() default "v1"
            // TODO: JSONObject elem1 = env.getJSONArray("elements").getJSONObject(1);
            // TODO: assertEquals("\"v1\"", elem1.getString("default_value"));
        }

        @Test
        void no_stereotype_returns_null() {
            String src = """
                    package com.example;
                    public class PlainClass {}
                    """;
            JSONObject env = parse(src);
            // TODO: assertTrue(env.isNull("stereotype"));
        }
    }

    // =========================================================================
    // Category B — Field / Method metadata
    // =========================================================================

    @Nested
    class FieldAndMethodMetadataTests {

        /** JPA entity with field-injection, qualifier, @Column, @Id, constraints. */
        private static final String ENTITY_SOURCE = """
                package com.example;
                import javax.persistence.*;
                import org.springframework.beans.factory.annotation.Autowired;
                import org.springframework.beans.factory.annotation.Qualifier;
                import javax.validation.constraints.*;
                @Entity
                @Table(name = "owners")
                public class Owner {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(name = "first_name", nullable = false, length = 50)
                    @NotBlank
                    private String firstName;

                    @Autowired
                    @Qualifier("primaryRepo")
                    private OwnerRepository ownerRepo;
                }
                """;

        /** REST controller with @GetMapping and @PostMapping handler methods. */
        private static final String CONTROLLER_SOURCE = """
                package com.example;
                import org.springframework.web.bind.annotation.*;
                @RestController
                @RequestMapping("/owners")
                public class OwnerController {
                    @GetMapping("/{id}")
                    public Owner getOwner(@PathVariable Long id) {
                        return null;
                    }
                    @PostMapping
                    @ResponseBody
                    public Owner createOwner(@RequestBody @Valid Owner owner) {
                        return null;
                    }
                }
                """;

        // --- field metadata ---

        @Test
        void id_field_flags() {
            JSONObject env = parse(ENTITY_SOURCE);
            JSONObject idField = findField(env, "id");
            // TODO: assertTrue(idField.getBoolean("is_id"));
            // TODO: assertFalse(idField.getBoolean("is_autowired"));
            // TODO: assertEquals("GenerationType.IDENTITY", idField.getString("generation"));
        }

        @Test
        void column_metadata_on_string_field() {
            JSONObject env = parse(ENTITY_SOURCE);
            JSONObject field = findField(env, "firstName");
            JSONObject col = field.getJSONObject("column");
            // TODO: assertEquals("first_name", col.getString("name"));
            // TODO: assertFalse(col.getBoolean("nullable"));
            // TODO: assertEquals(50, col.getInt("length"));
        }

        @Test
        void constraint_annotation_on_field() {
            JSONObject env = parse(ENTITY_SOURCE);
            JSONObject field = findField(env, "firstName");
            // TODO: assertTrue(toList(field.getJSONArray("constraints")).contains("NotBlank"));
        }

        @Test
        void autowired_field_injection_type_and_qualifier() {
            JSONObject env = parse(ENTITY_SOURCE);
            JSONObject field = findField(env, "ownerRepo");
            // TODO: assertTrue(field.getBoolean("is_autowired"));
            // TODO: assertEquals("field", field.getString("injection_type"));
            // TODO: assertEquals("primaryRepo", field.getString("qualifier"));
        }

        @Test
        void table_name_from_entity_annotation() {
            JSONObject env = parse(ENTITY_SOURCE);
            // TODO: assertEquals("owners", env.getString("table_name"));
        }

        // --- method metadata ---

        @Test
        void get_mapping_http_metadata() {
            JSONObject env = parse(CONTROLLER_SOURCE);
            JSONObject method = findMethod(env, "getOwner");
            JSONObject http = method.getJSONObject("http_metadata");
            // TODO: assertEquals("GET", http.getString("method"));
            // TODO: assertEquals("/{id}", http.getString("path"));
        }

        @Test
        void post_mapping_http_metadata() {
            JSONObject env = parse(CONTROLLER_SOURCE);
            JSONObject method = findMethod(env, "createOwner");
            JSONObject http = method.getJSONObject("http_metadata");
            // TODO: assertEquals("POST", http.getString("method"));
            // TODO: assertEquals("", http.getString("path"));  // no path on @PostMapping
        }

        @Test
        void path_variable_parameter_binding() {
            JSONObject env = parse(CONTROLLER_SOURCE);
            JSONObject method = findMethod(env, "getOwner");
            JSONObject param = method.getJSONArray("parameters").getJSONObject(0);
            JSONObject binding = param.getJSONObject("binding");
            // TODO: assertEquals("path", binding.getString("kind"));
            // TODO: assertEquals("Long",  param.getString("type"));
        }

        @Test
        void request_body_parameter_binding_with_valid() {
            JSONObject env = parse(CONTROLLER_SOURCE);
            JSONObject method = findMethod(env, "createOwner");
            JSONObject param = method.getJSONArray("parameters").getJSONObject(0);
            // TODO: assertTrue(param.getBoolean("validate"));
            JSONObject binding = param.getJSONObject("binding");
            // TODO: assertEquals("body", binding.getString("kind"));
        }

        @Test
        void response_body_flag() {
            JSONObject env = parse(CONTROLLER_SOURCE);
            JSONObject method = findMethod(env, "createOwner");
            // TODO: assertTrue(method.getBoolean("response_body"));
        }

        @Test
        void non_handler_method_has_null_http_metadata() {
            String src = """
                    package com.example;
                    @org.springframework.stereotype.Service
                    public class Svc {
                        public void doWork() {}
                    }
                    """;
            JSONObject env = parse(src);
            JSONObject method = findMethod(env, "doWork");
            // TODO: assertTrue(method.isNull("http_metadata"));
        }
    }

    // =========================================================================
    // Category C — Complexity metrics
    // =========================================================================

    @Nested
    class ComplexityMetricsTests {

        // Hand-calculated expected values are given in the comments for each fixture.

        /**
         * Trivial method — no decisions.
         * Cyclomatic: 1  (base only)
         * Cognitive:  0
         * LOC:        3  (declaration + return + closing brace)
         */
        @Test
        void trivial_method_baseline() {
            MethodDeclaration m = parseMethod("""
                    public int getValue() {
                        return value;
                    }
                    """);
            // TODO: assertEquals(1, JavaParserRunner.computeCyclomatic(m));
            // TODO: assertEquals(0, JavaParserRunner.computeCognitive(m));
            // TODO: assertEquals(3, JavaParserRunner.computeMethodLoc(m));
        }

        /**
         * Single if-else.
         * Cyclomatic: 1 (base) + 1 (if) = 2
         * Cognitive:  1 (if+0 nesting) + 1 (else) = 2
         */
        @Test
        void single_if_else_cyclomatic_and_cognitive() {
            MethodDeclaration m = parseMethod("""
                    public String label(int x) {
                        if (x > 0) {
                            return "positive";
                        } else {
                            return "non-positive";
                        }
                    }
                    """);
            // TODO: assertEquals(2, JavaParserRunner.computeCyclomatic(m));
            // TODO: assertEquals(2, JavaParserRunner.computeCognitive(m));
        }

        /**
         * if / else-if / else chain.
         * Cyclomatic: 1 + 2 (two IfStmt nodes) = 3
         * Cognitive:  1+0 (if) + 1 (else-if, no nesting increment) + 1 (else) = 3
         */
        @Test
        void if_elseif_else_chain() {
            MethodDeclaration m = parseMethod("""
                    public String grade(int score) {
                        if (score >= 90) {
                            return "A";
                        } else if (score >= 70) {
                            return "B";
                        } else {
                            return "C";
                        }
                    }
                    """);
            // TODO: assertEquals(3, JavaParserRunner.computeCyclomatic(m));
            // TODO: assertEquals(3, JavaParserRunner.computeCognitive(m));
        }

        /**
         * Nested if inside a for loop.
         * Cyclomatic: 1 + 1 (for) + 1 (if) = 3
         * Cognitive:  1+0 (for) + 1+1 (if at depth 1) = 3
         */
        @Test
        void nested_if_inside_for() {
            MethodDeclaration m = parseMethod("""
                    public int countPositive(int[] arr) {
                        int count = 0;
                        for (int x : arr) {
                            if (x > 0) {
                                count++;
                            }
                        }
                        return count;
                    }
                    """);
            // TODO: assertEquals(3, JavaParserRunner.computeCyclomatic(m));
            // TODO: assertEquals(3, JavaParserRunner.computeCognitive(m));
        }

        /**
         * Logical operator sequence: a && b && c counts as ONE operator run.
         * Cyclomatic: 1 + 2 (two && BinaryExprs) = 3
         * Cognitive:  1+0 (if) + 1 (one && run regardless of operator count) = 2
         *
         * Note: cyclomatic counts each && individually; cognitive counts the run as 1.
         * This divergence is the core spec difference between the two metrics.
         */
        @Test
        void logical_operator_run_cognitive_vs_cyclomatic() {
            MethodDeclaration m = parseMethod("""
                    public boolean isValid(String s, int min, int max) {
                        if (s != null && s.length() >= min && s.length() <= max) {
                            return true;
                        }
                        return false;
                    }
                    """);
            // TODO: assertEquals(3, JavaParserRunner.computeCyclomatic(m));  // 1 + 2 &&
            // TODO: assertEquals(2, JavaParserRunner.computeCognitive(m));   // if(1) + run(1)
        }

        /**
         * Method LOC counts physical lines (declaration through closing brace).
         */
        @Test
        void method_loc_counts_physical_lines() {
            MethodDeclaration m = parseMethod("""
                    public void fiveLines() {
                        // line 2
                        int x = 1;
                        // line 4
                    }
                    """);
            // TODO: assertEquals(5, JavaParserRunner.computeMethodLoc(m));
        }

        /**
         * WMC = sum of cyclomatic complexities of all methods.
         * Two methods: cc=1, cc=2 → WMC = 3.
         */
        @Test
        void wmc_is_sum_of_method_cyclomatics() {
            JSONObject env = parse("""
                    package com.example;
                    public class Calc {
                        public int simple() { return 1; }
                        public int branch(boolean b) { if (b) return 1; return 0; }
                    }
                    """);
            // TODO: assertEquals(3, env.getInt("wmc"));
        }

        /**
         * CBO counts distinct non-trivial types from fields, params, return types.
         * OwnerRepository + Pageable are domain types; String/List are excluded.
         * Expected CBO = 2.
         */
        @Test
        void cbo_excludes_stdlib_and_primitives() {
            JSONObject env = parse("""
                    package com.example;
                    import java.util.List;
                    public class OwnerService {
                        private OwnerRepository repo;
                        public List<String> findAll() { return null; }
                        public Owner findById(Long id) { return null; }
                    }
                    """);
            // TODO: assertEquals(2, env.getInt("cbo"));  // OwnerRepository + Owner
        }

        /**
         * Switch statement — each non-default case label increments cyclomatic by 1.
         * Three case labels (A, B, default is excluded) → CC = 1 + 2 = 3.
         */
        @Test
        void switch_case_labels() {
            MethodDeclaration m = parseMethod("""
                    public String name(int code) {
                        switch (code) {
                            case 1: return "one";
                            case 2: return "two";
                            default: return "other";
                        }
                    }
                    """);
            // TODO: assertEquals(3, JavaParserRunner.computeCyclomatic(m));
        }
    }

    // =========================================================================
    // Category D — LCOM4
    // =========================================================================

    @Nested
    class Lcom4Tests {

        /**
         * Cohesive class: all three methods touch the same field {@code balance}.
         * Graph: deposit — withdraw — getBalance (all connected through balance).
         * Expected LCOM4 = 1.
         */
        private static final String COHESIVE_SOURCE = """
                package com.example;
                public class BankAccount {
                    private double balance;

                    public void   deposit(double amount)  { balance += amount; }
                    public void   withdraw(double amount) { balance -= amount; }
                    public double getBalance()            { return balance; }
                }
                """;

        /**
         * Split class: two independent method groups, each touching a different field.
         * Group 1 (order): validate, persist.
         * Group 2 (mailer): sendConfirmation, sendReceipt.
         * Expected LCOM4 = 2.
         */
        private static final String SPLIT_SOURCE = """
                package com.example;
                public class MixedService {
                    private String order;
                    private String mailer;

                    public void validate()         { System.out.println(order); }
                    public void persist()          { System.out.println(order); }
                    public void sendConfirmation() { System.out.println(mailer); }
                    public void sendReceipt()      { System.out.println(mailer); }
                }
                """;

        /**
         * God class: three completely isolated method groups, one per field.
         * Group 1 (userRepo): findUser, saveUser.
         * Group 2 (emailService): sendWelcome, sendAlert.
         * Group 3 (reportEngine): exportPdf, exportCsv.
         * Expected LCOM4 = 3.
         */
        private static final String GOD_SOURCE = """
                package com.example;
                public class ApplicationFacade {
                    private String userRepo;
                    private String emailService;
                    private String reportEngine;

                    public void findUser()    { System.out.println(userRepo); }
                    public void saveUser()    { System.out.println(userRepo); }
                    public void sendWelcome() { System.out.println(emailService); }
                    public void sendAlert()   { System.out.println(emailService); }
                    public void exportPdf()   { System.out.println(reportEngine); }
                    public void exportCsv()   { System.out.println(reportEngine); }
                }
                """;

        @Test
        void lcom4_cohesiveClass_returns1() {
            CompilationUnit cu = StaticJavaParser.parse(COHESIVE_SOURCE);
            ClassOrInterfaceDeclaration decl =
                    cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
            JSONArray methods = JavaParserRunner.buildMethods(decl, "com.example.BankAccount");
            // TODO (learner): assertEquals(1, JavaParserRunner.computeLcom4(methods));
        }

        @Test
        void lcom4_splitClass_returns2() {
            CompilationUnit cu = StaticJavaParser.parse(SPLIT_SOURCE);
            ClassOrInterfaceDeclaration decl =
                    cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
            JSONArray methods = JavaParserRunner.buildMethods(decl, "com.example.MixedService");
            // TODO (learner): assertEquals(2, JavaParserRunner.computeLcom4(methods));
        }

        @Test
        void lcom4_godClass_returns3OrMore() {
            CompilationUnit cu = StaticJavaParser.parse(GOD_SOURCE);
            ClassOrInterfaceDeclaration decl =
                    cu.findFirst(ClassOrInterfaceDeclaration.class).orElseThrow();
            JSONArray methods = JavaParserRunner.buildMethods(decl, "com.example.ApplicationFacade");
            // TODO (learner): assertTrue(JavaParserRunner.computeLcom4(methods) >= 3);
        }
    }

    // =========================================================================
    // Test helpers
    // =========================================================================

    /** Parse a full compilation unit and return the top-level envelope. */
    private static JSONObject parse(String source) {
        CompilationUnit cu = StaticJavaParser.parse(source);
        return JavaParserRunner.buildEnvelope(cu, "test/Test.java");
    }

    /**
     * Parse a bare method declaration string.
     * Wraps it in a minimal class so JavaParser can resolve context.
     */
    private static MethodDeclaration parseMethod(String methodSource) {
        String wrapped = "class _Wrap_ { " + methodSource + " }";
        CompilationUnit cu = StaticJavaParser.parse(wrapped);
        ClassOrInterfaceDeclaration cls = cu.getClassByName("_Wrap_")
                .orElseThrow(() -> new IllegalStateException("wrapper class not found"));
        return cls.getMethods().get(0);
    }

    /**
     * Find a field object by name in the fields array.
     * Throws if the field is not found — fail-fast so the calling test gets a
     * descriptive error rather than a NullPointerException.
     */
    private static JSONObject findField(JSONObject env, String name) {
        JSONArray fields = env.getJSONArray("fields");
        for (int i = 0; i < fields.length(); i++) {
            JSONObject f = fields.getJSONObject(i);
            if (name.equals(f.getString("name"))) return f;
        }
        throw new AssertionError("field not found: " + name);
    }

    /**
     * Find a method object by name in the methods array.
     * Returns the first match (overloads not distinguished).
     */
    private static JSONObject findMethod(JSONObject env, String name) {
        JSONArray methods = env.getJSONArray("methods");
        for (int i = 0; i < methods.length(); i++) {
            JSONObject m = methods.getJSONObject(i);
            if (name.equals(m.getString("name"))) return m;
        }
        throw new AssertionError("method not found: " + name);
    }

    /** Convert a JSONArray of strings to a java.util.List for contains() checks. */
    private static java.util.List<String> toList(JSONArray arr) {
        java.util.List<String> list = new java.util.ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) list.add(arr.getString(i));
        return list;
    }
}
