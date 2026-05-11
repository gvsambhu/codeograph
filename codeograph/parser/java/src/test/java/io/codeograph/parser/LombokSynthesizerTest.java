package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for {@link LombokSynthesizer} — one fixture per supported annotation.
 *
 * <p>Each test verifies that the synthesised methods appear in the assembled
 * methods array with {@code is_synthesised: true} and the expected signature.
 *
 * <p>All assertions are left as TODOs for the learner (Issue #2).
 * Tests will compile and run green (no-op synthesizer) until the learner implements
 * {@link LombokSynthesizer#synthesize}.
 */
class LombokSynthesizerTest {

    @BeforeAll
    static void configureParser() {
        StaticJavaParser.setConfiguration(
                new ParserConfiguration()
                        .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
    }

    // -------------------------------------------------------------------------
    // @Getter (class-level)
    // -------------------------------------------------------------------------

    @Test
    void getter_class_level_synthesises_getters_for_all_fields() {
        JSONObject env = parse("""
                package com.example;
                import lombok.Getter;
                @Getter
                public class Product {
                    private String name;
                    private double price;
                }
                """);
        assertTrue(methodNames(env).contains("getName"));
        assertTrue(methodNames(env).contains("getPrice"));
        assertTrue(findMethod(env, "getName").getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // @Setter (class-level)
    // -------------------------------------------------------------------------

    @Test
    void setter_class_level_synthesises_setters_for_non_final_fields() {
        JSONObject env = parse("""
                package com.example;
                import lombok.Setter;
                @Setter
                public class Product {
                    private String name;
                    private final double price = 0.0;
                }
                """);
        assertTrue(methodNames(env).contains("setName"));
        assertFalse(methodNames(env).contains("setPrice")); // final field excluded
        assertTrue(findMethod(env, "setName").getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // @NoArgsConstructor
    // -------------------------------------------------------------------------

    @Test
    void no_args_constructor_synthesised() {
        JSONObject env = parse("""
                package com.example;
                import lombok.NoArgsConstructor;
                @NoArgsConstructor
                public class Product {
                    private String name;
                }
                """);
        assertEquals(1, countConstructors(env));
        JSONObject ctor = findConstructor(env);
        assertEquals(0, ctor.getJSONArray("parameters").length());
        assertTrue(ctor.getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // @AllArgsConstructor
    // -------------------------------------------------------------------------

    @Test
    void all_args_constructor_synthesised() {
        JSONObject env = parse("""
                package com.example;
                import lombok.AllArgsConstructor;
                @AllArgsConstructor
                public class Product {
                    private String name;
                    private double price;
                }
                """);
        JSONObject ctor = findConstructor(env);
        assertEquals(2, ctor.getJSONArray("parameters").length());
        assertTrue(ctor.getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // @RequiredArgsConstructor
    // -------------------------------------------------------------------------

    @Test
    void required_args_constructor_includes_only_final_and_nonnull_fields() {
        JSONObject env = parse("""
                package com.example;
                import lombok.RequiredArgsConstructor;
                import lombok.NonNull;
                @RequiredArgsConstructor
                public class Product {
                    private final String name;
                    @NonNull private String category;
                    private double price;
                }
                """);
        JSONObject ctor = findConstructor(env);
        assertEquals(2, ctor.getJSONArray("parameters").length()); // name + category only
        assertTrue(ctor.getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // @Data
    // -------------------------------------------------------------------------

    @Test
    void data_synthesises_getters_setters_and_required_constructor() {
        JSONObject env = parse("""
                package com.example;
                import lombok.Data;
                @Data
                public class Product {
                    private final String name;
                    private double price;
                }
                """);
        assertTrue(methodNames(env).contains("getName"));
        assertTrue(methodNames(env).contains("getPrice"));
        assertTrue(methodNames(env).contains("setPrice"));  // non-final
        assertFalse(methodNames(env).contains("setName")); // final — excluded
        JSONObject ctor = findConstructor(env);
        assertEquals(1, ctor.getJSONArray("parameters").length()); // only 'name'
    }

    // -------------------------------------------------------------------------
    // @Value
    // -------------------------------------------------------------------------

    @Test
    void value_synthesises_getters_and_all_args_constructor_no_setters() {
        JSONObject env = parse("""
                package com.example;
                import lombok.Value;
                @Value
                public class Product {
                    String name;
                    double price;
                }
                """);
        assertTrue(methodNames(env).contains("getName"));
        assertTrue(methodNames(env).contains("getPrice"));
        assertFalse(methodNames(env).stream().anyMatch(n -> n.startsWith("set")));
        JSONObject ctor = findConstructor(env);
        assertEquals(2, ctor.getJSONArray("parameters").length());
    }

    // -------------------------------------------------------------------------
    // @Builder
    // -------------------------------------------------------------------------

    @Test
    void builder_synthesises_static_builder_entry_point() {
        JSONObject env = parse("""
                package com.example;
                import lombok.Builder;
                @Builder
                public class Product {
                    private String name;
                    private double price;
                }
                """);
        assertTrue(methodNames(env).contains("builder"));
        JSONObject builderMethod = findMethod(env, "builder");
        assertTrue(toList(builderMethod.getJSONArray("modifiers")).contains("static"));
        assertTrue(builderMethod.getBoolean("is_synthesised"));
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private static JSONObject parse(String source) {
        CompilationUnit cu = StaticJavaParser.parse(source);
        return ParsedFileAssembler.buildEnvelope(cu, "test/Test.java");
    }

    private static List<String> methodNames(JSONObject env) {
        JSONArray methods = env.getJSONArray("methods");
        List<String> names = new ArrayList<>();
        for (int i = 0; i < methods.length(); i++) {
            names.add(methods.getJSONObject(i).getString("name"));
        }
        return names;
    }

    private static JSONObject findMethod(JSONObject env, String name) {
        JSONArray methods = env.getJSONArray("methods");
        for (int i = 0; i < methods.length(); i++) {
            JSONObject m = methods.getJSONObject(i);
            if (name.equals(m.getString("name"))) return m;
        }
        throw new AssertionError("method not found: " + name);
    }

    private static JSONObject findConstructor(JSONObject env) {
        JSONArray methods = env.getJSONArray("methods");
        for (int i = 0; i < methods.length(); i++) {
            JSONObject m = methods.getJSONObject(i);
            if (m.getBoolean("is_constructor")) return m;
        }
        throw new AssertionError("no constructor found");
    }

    private static long countConstructors(JSONObject env) {
        JSONArray methods = env.getJSONArray("methods");
        long count = 0;
        for (int i = 0; i < methods.length(); i++) {
            if (methods.getJSONObject(i).getBoolean("is_constructor")) count++;
        }
        return count;
    }

    private static List<String> toList(JSONArray arr) {
        List<String> list = new ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) list.add(arr.getString(i));
        return list;
    }
}
