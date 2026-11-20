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
 * Tests for {@link ParsedFileAssembler} — structural extraction and
 * field/method metadata.
 *
 * <p>
 * Category A: kind, id, name, annotations, imports, stereotype, superclass,
 * implements, constants, components.
 * <p>
 * Category B: injection flags, qualifier, JPA column, Bean Validation
 * constraints, HTTP metadata, parameter bindings.
 */
class ParsedFileAssemblerTest {

	@BeforeAll
	static void configureParser() {
		StaticJavaParser.setConfiguration(
				new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
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
			assertEquals("class", env.getString("kind"));
			assertEquals("com.example.OwnerService", env.getString("id"));
			assertEquals("OwnerService", env.getString("name"));
			assertEquals("ast", env.getString("extraction_mode"));
		}

		@Test
		void class_stereotype_and_annotation() {
			JSONObject env = parse(SERVICE_SOURCE);
			assertEquals("Service", env.getString("stereotype"));
			assertTrue(toList(env.getJSONArray("annotations")).contains("Service"));
		}

		@Test
		void class_superclass_and_implements() {
			JSONObject env = parse(SERVICE_SOURCE);
			assertEquals(1, env.getJSONArray("implements").length());
		}

		/**
		 * The parser reports the superclass as written; the graph stage resolves it.
		 */
		@Test
		void class_superclass_is_reported_as_written() {
			JSONObject env = parse(SERVICE_SOURCE);
			assertEquals("BaseService", env.getString("superclass"));
		}

		@Test
		void class_implements_are_reported_as_written() {
			JSONObject env = parse(SERVICE_SOURCE);
			assertEquals("Auditable", env.getJSONArray("implements").getString(0));
		}

		/** A qualifier written in the source is kept; type arguments are not. */
		@Test
		void qualified_supertypes_keep_their_qualifier() {
			JSONObject env = parse("""
					package com.example;
					public class Report extends org.example.Base<String> implements java.io.Serializable {
					}
					""");
			assertEquals("org.example.Base", env.getString("superclass"));
			assertEquals("java.io.Serializable", env.getJSONArray("implements").getString(0));
		}

		@Test
		void interface_extends_are_reported_as_written() {
			JSONObject env = parse(INTERFACE_SOURCE);
			assertEquals("Serializable", env.getJSONArray("extends_interfaces").getString(0));
			assertEquals("Cloneable", env.getJSONArray("extends_interfaces").getString(1));
		}

		@Test
		void class_imports() {
			JSONObject env = parse(SERVICE_SOURCE);
			List<String> imports = toList(env.getJSONArray("imports"));
			assertTrue(imports.contains("com.example.repo.OwnerRepository"));
			assertTrue(imports.contains("org.springframework.stereotype.Service"));
		}

		/**
		 * Each non-static on-demand import is reported by its package, in source order;
		 * single-type and static imports are not.
		 */
		@Test
		void wildcard_imports_are_the_packages_of_non_static_on_demand_imports() {
			String source = """
					package com.example;
					import java.util.*;
					import com.example.repo.OwnerRepository;
					import static java.lang.Math.*;
					import com.example.model.*;
					public class Report {
					}
					""";
			assertEquals(List.of("java.util", "com.example.model"),
					toList(parse(source).getJSONArray("wildcard_imports")));
			assertEquals(List.of(), toList(parse(SERVICE_SOURCE).getJSONArray("wildcard_imports")));
		}

		@Test
		void interface_wildcard_imports_are_reported_too() {
			String source = """
					package com.example;
					import java.util.*;
					public interface Auditable {
					}
					""";
			assertEquals(List.of("java.util"), toList(parse(source).getJSONArray("wildcard_imports")));
		}

		@Test
		void interface_kind_and_extends() {
			JSONObject env = parse(INTERFACE_SOURCE);
			assertEquals("interface", env.getString("kind"));
			assertEquals(2, env.getJSONArray("extends_interfaces").length());
		}

		@Test
		void enum_kind_and_constants() {
			JSONObject env = parse(ENUM_SOURCE);
			assertEquals("enum", env.getString("kind"));
			assertEquals(3, env.getJSONArray("constants").length());
			assertEquals("ACTIVE", env.getJSONArray("constants").getString(0));
		}

		@Test
		void enum_implements() {
			JSONObject env = parse(ENUM_SOURCE);
			assertEquals(1, env.getJSONArray("implements").length());
		}

		@Test
		void enum_implements_are_reported_as_written() {
			JSONObject env = parse(ENUM_SOURCE);
			assertEquals("Displayable", env.getJSONArray("implements").getString(0));
		}

		@Test
		void record_kind_and_components() {
			JSONObject env = parse(RECORD_SOURCE);
			assertEquals("record", env.getString("kind"));
			assertEquals(2, env.getJSONArray("components").length());
			assertEquals("page", env.getJSONArray("components").getJSONObject(0).getString("name"));
			assertEquals("int", env.getJSONArray("components").getJSONObject(0).getString("type"));
		}

		@Test
		void annotation_type_kind_and_elements() {
			JSONObject env = parse(ANNOTATION_TYPE_SOURCE);
			assertEquals("annotation_type", env.getString("kind"));
			assertEquals(2, env.getJSONArray("elements").length());
			JSONObject elem0 = env.getJSONArray("elements").getJSONObject(0);
			assertEquals("value", elem0.getString("name"));
			assertEquals("int", elem0.getString("type"));
			assertTrue(elem0.isNull("default_value"));
			JSONObject elem1 = env.getJSONArray("elements").getJSONObject(1);
			assertEquals("\"v1\"", elem1.getString("default_value"));
		}

		@Test
		void no_stereotype_returns_null() {
			JSONObject env = parse("""
					package com.example;
					public class PlainClass {}
					""");
			assertTrue(env.isNull("stereotype"));
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
			assertTrue(idField.getBoolean("is_id"));
			assertFalse(idField.getBoolean("is_autowired"));
			assertEquals("GenerationType.IDENTITY", idField.getString("generation"));
		}

		@Test
		void column_metadata_on_string_field() {
			JSONObject env = parse(ENTITY_SOURCE);
			JSONObject field = findField(env, "firstName");
			JSONObject col = field.getJSONObject("column");
			assertEquals("first_name", col.getString("name"));
			assertFalse(col.getBoolean("nullable"));
			assertEquals(50, col.getInt("length"));
		}

		@Test
		void constraint_annotation_on_field() {
			JSONObject env = parse(ENTITY_SOURCE);
			JSONObject field = findField(env, "firstName");
			assertTrue(toList(field.getJSONArray("constraints")).contains("NotBlank"));
		}

		@Test
		void autowired_field_injection_type_and_qualifier() {
			JSONObject env = parse(ENTITY_SOURCE);
			JSONObject field = findField(env, "ownerRepo");
			assertTrue(field.getBoolean("is_autowired"));
			assertEquals("field", field.getString("injection_type"));
			assertEquals("primaryRepo", field.getString("qualifier"));
		}

		@Test
		void table_name_from_entity_annotation() {
			JSONObject env = parse(ENTITY_SOURCE);
			assertEquals("owners", env.getString("table_name"));
		}

		@Test
		void get_mapping_http_metadata() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject method = findMethod(env, "getOwner");
			JSONObject http = method.getJSONObject("http_metadata");
			assertEquals("GET", http.getString("method"));
		}

		@Test
		void get_mapping_path_includes_class_level_mapping() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject http = findMethod(env, "getOwner").getJSONObject("http_metadata");
			assertEquals("/owners/{id}", http.getString("path"));
		}

		@Test
		void http_path_without_class_level_mapping_is_the_method_path() {
			JSONObject env = parse("""
					package com.example;
					import org.springframework.web.bind.annotation.*;
					@RestController
					public class PingController {
					    @GetMapping("/ping")
					    public String ping() { return null; }
					}
					""");
			assertEquals("/ping", findMethod(env, "ping").getJSONObject("http_metadata").getString("path"));
		}

		@Test
		void http_path_joins_with_one_slash_at_the_seam() {
			JSONObject env = parse("""
					package com.example;
					import org.springframework.web.bind.annotation.*;
					@RestController
					@RequestMapping(path = "/api/")
					public class ApiController {
					    @GetMapping("/items")
					    public String items() { return null; }
					    @GetMapping("details")
					    public String details() { return null; }
					}
					""");
			assertEquals("/api/items", findMethod(env, "items").getJSONObject("http_metadata").getString("path"));
			assertEquals("/api/details", findMethod(env, "details").getJSONObject("http_metadata").getString("path"));
		}

		@Test
		void http_path_uses_first_element_of_an_array_mapping() {
			JSONObject env = parse("""
					package com.example;
					import org.springframework.web.bind.annotation.*;
					@RestController
					@RequestMapping({"/v1", "/v2"})
					public class VersionedController {
					    @GetMapping("/status")
					    public String status() { return null; }
					}
					""");
			assertEquals("/v1/status", findMethod(env, "status").getJSONObject("http_metadata").getString("path"));
		}

		@Test
		void post_mapping_http_metadata() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject method = findMethod(env, "createOwner");
			JSONObject http = method.getJSONObject("http_metadata");
			assertEquals("POST", http.getString("method"));
		}

		@Test
		void post_mapping_path_includes_class_level_mapping() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject http = findMethod(env, "createOwner").getJSONObject("http_metadata");
			assertEquals("/owners", http.getString("path"));
		}

		@Test
		void path_variable_parameter_binding() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject method = findMethod(env, "getOwner");
			JSONObject param = method.getJSONArray("parameters").getJSONObject(0);
			JSONObject binding = param.getJSONObject("binding");
			assertEquals("path", binding.getString("kind"));
			assertEquals("Long", param.getString("type"));
		}

		@Test
		void request_body_parameter_binding_with_valid() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject method = findMethod(env, "createOwner");
			JSONObject param = method.getJSONArray("parameters").getJSONObject(0);
			assertTrue(param.getBoolean("validate"));
			JSONObject binding = param.getJSONObject("binding");
			assertEquals("body", binding.getString("kind"));
		}

		@Test
		void response_body_flag() {
			JSONObject env = parse(CONTROLLER_SOURCE);
			JSONObject method = findMethod(env, "createOwner");
			assertTrue(method.getBoolean("response_body"));
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
			assertTrue(method.isNull("http_metadata"));
		}

		@Test
		void bodyless_method_omits_complexity_metrics() {
			JSONObject env = parse("""
					package com.example;
					public interface Auditable {
					    void audit();
					}
					""");
			JSONObject method = findMethod(env, "audit");
			assertTrue(method.isNull("cyclomatic_complexity"), "bodyless method must have null cyclomatic_complexity");
			assertTrue(method.isNull("cognitive_complexity"), "bodyless method must have null cognitive_complexity");
			assertTrue(method.isNull("method_loc"), "bodyless method must have null method_loc");
		}

		@Test
		void methodless_class_emits_null_wmc_and_lcom4() {
			// D-004-1: a class with no methods and no constructors
			// must emit null for wmc and lcom4 — not 0 / 1 — to avoid eval skew.
			// cbo is always computed (not in D-004-1's omission list).
			JSONObject env = parse("""
					package com.example;
					public class Marker {
					    private String tag;
					}
					""");
			assertTrue(env.isNull("wmc"), "method-less class must have null wmc");
			assertTrue(env.isNull("lcom4"), "method-less class must have null lcom4");
			assertFalse(env.isNull("cbo"), "cbo must always be present (not in D-004-1 omission list)");
		}

		@Test
		void constructor_only_class_has_integer_wmc_and_lcom4() {
			// A constructor-only class has a declared constructor → WMC = its CC (int),
			// NOT null. Per ADR-004 §3.3: WMC includes constructors.
			JSONObject env = parse("""
					package com.example;
					public class Token {
					    private final String value;
					    public Token(String value) { this.value = value; }
					}
					""");
			assertFalse(env.isNull("wmc"),
					"constructor-only class must have integer wmc (constructor is a method per ADR-004 §3.3)");
			assertTrue(env.get("wmc") instanceof Integer,
					"wmc must be an integer (the constructor's cyclomatic complexity)");
			assertFalse(env.isNull("lcom4"), "constructor-only class must have integer lcom4 (constructor is a node)");
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
			if (name.equals(f.getString("name")))
				return f;
		}
		throw new AssertionError("field not found: " + name);
	}

	private static JSONObject findMethod(JSONObject env, String name) {
		JSONArray methods = env.getJSONArray("methods");
		for (int i = 0; i < methods.length(); i++) {
			JSONObject m = methods.getJSONObject(i);
			if (name.equals(m.getString("name")))
				return m;
		}
		throw new AssertionError("method not found: " + name);
	}

	private static List<String> toList(JSONArray arr) {
		List<String> list = new ArrayList<>(arr.length());
		for (int i = 0; i < arr.length(); i++)
			list.add(arr.getString(i));
		return list;
	}
}
