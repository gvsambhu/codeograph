package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for {@link ParsedFileAssembler} — structural extraction and field/method metadata.
 *
 * <p>Category A: kind, id, name, annotations, imports, stereotype, superclass,
 * implements, constants, components.
 * <p>Category B: injection flags, qualifier, JPA column, Bean Validation constraints,
 * HTTP metadata, parameter bindings.
 */
class ParsedFileAssemblerTest {

    @BeforeAll
    static void configureParser() {
        StaticJavaParser.setConfiguration(
                new ParserConfiguration()
                        .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
    }

    // =========================================================================
    // Category A — Structural extraction
    // =========================================================================

    @Nested
    class StructuralExtractionTests {

        private static final String SERVICE_SOURCE = """
                package com.example;
                import com.example.repo.OwnerRepository;
                import org.springframework.stereotype.Service;
                @Service
                public class OwnerService extends BaseService implements Auditable {
                    private OwnerRepository ownerRepo;
                }
                """;

        private static final String INTERFACE_SOURCE = """
                package com.example;
                public interface Auditable extends Serializable, Cloneable {
                    void audit();
                }
                """;

        private static final String ENUM_SOURCE = """
                package com.example;
                public enum Status implements Displayable {
                    ACTIVE, INACTIVE, PENDING;
                }
                """;

        private static final String RECORD_SOURCE = """
                package com.example;
                public record PageRequest(int page, int size) {}
                """;

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
            // TODO: JSONObject elem0 = env.getJSONArray("elements").getJSONObject(0);
            // TODO: assertEquals("value", elem0.getString("name"));
            // TODO: assertEquals("int",   elem0.getString("type"));
            // TODO: assertTrue(elem0.isNull("default_value"));
            // TODO: JSONObject elem1 = env.getJSONArray("elements").getJSONObject(1);
            // TODO: assertEquals("\"v1\"", elem1.getString("default_value"));
        }

        @Test
        void no_stereotype_returns_null() {
            JSONObject env = parse("""
                    package com.example;
                    public class PlainClass {}
                    """);
            // TODO: assertTrue(env.isNull("stereotype"));
        }
    }

    // =========================================================================
    // Category B — Field / Method metadata
    // =========================================================================

    @Nested
    class FieldAndMethodMetadataTests {

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
            // TODO: assertEquals("", http.getString("path"));
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
            JSONObject env = parse("""
                    package com.example;
                    @org.springframework.stereotype.Service
                    public class Svc {
                        public void doWork() {}
                    }
                    """);
            JSONObject method = findMethod(env, "doWork");
            // TODO: assertTrue(method.isNull("http_metadata"));
        }
    }

    // =========================================================================
    // Test helpers
    // =========================================================================

    private static JSONObject parse(String source) {
        CompilationUnit cu = StaticJavaParser.parse(source);
        return ParsedFileAssembler.buildEnvelope(cu, "test/Test.java");
    }

    private static JSONObject findField(JSONObject env, String name) {
        JSONArray fields = env.getJSONArray("fields");
        for (int i = 0; i < fields.length(); i++) {
            JSONObject f = fields.getJSONObject(i);
            if (name.equals(f.getString("name"))) return f;
        }
        throw new AssertionError("field not found: " + name);
    }

    private static JSONObject findMethod(JSONObject env, String name) {
        JSONArray methods = env.getJSONArray("methods");
        for (int i = 0; i < methods.length(); i++) {
            JSONObject m = methods.getJSONObject(i);
            if (name.equals(m.getString("name"))) return m;
        }
        throw new AssertionError("method not found: " + name);
    }

    private static List<String> toList(JSONArray arr) {
        List<String> list = new ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) list.add(arr.getString(i));
        return list;
    }
}
