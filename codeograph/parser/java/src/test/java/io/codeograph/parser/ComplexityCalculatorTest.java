package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for {@link ComplexityCalculator} — cyclomatic, cognitive, LOC, WMC,
 * CBO.
 *
 * <p>
 * All expected values are hand-calculated and annotated in the fixture
 * comments. WMC and CBO are verified via the assembled envelope (they're
 * class-level aggregates).
 */
class ComplexityCalculatorTest {

	@BeforeAll
	static void configureParser() {
		StaticJavaParser.setConfiguration(
				new ParserConfiguration().setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
	}

	/**
	 * Trivial method — no decisions. Cyclomatic: 1 (base only) Cognitive: 0 LOC: 3
	 */
	@Test
	void trivial_method_baseline() {
		MethodDeclaration m = parseMethod("""
				public int getValue() {
				    return value;
				}
				""");
		assertEquals(1, ComplexityCalculator.computeCyclomatic(m));
		assertEquals(0, ComplexityCalculator.computeCognitive(m));
		assertEquals(3, ComplexityCalculator.computeMethodLoc(m));
	}

	/**
	 * Single if-else. Cyclomatic: 1 + 1 (if) = 2 Cognitive: 1 (if+0) + 1 (else) = 2
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
		assertEquals(2, ComplexityCalculator.computeCyclomatic(m));
		assertEquals(2, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * if / else-if / else chain. Cyclomatic: 1 + 2 (two IfStmt nodes) = 3
	 * Cognitive: 1+0 (if) + 1 (else-if) + 1 (else) = 3
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
		assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * Nested if inside a for loop. Cyclomatic: 1 + 1 (for) + 1 (if) = 3 Cognitive:
	 * 1+0 (for) + 1+1 (if at depth 1) = 3
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
		assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	private static final String LOGICAL_RUN_METHOD = """
			public boolean isValid(String s, int min, int max) {
			    if (s != null && s.length() >= min && s.length() <= max) {
			        return true;
			    }
			    return false;
			}
			""";

	/**
	 * Cyclomatic: 1 + 1 (if) + 2 (two &&) = 4.
	 */
	@Test
	void logical_operator_run_cyclomatic() {
		assertEquals(4, ComplexityCalculator.computeCyclomatic(parseMethod(LOGICAL_RUN_METHOD)));
	}

	/**
	 * Logical operator sequence: a && b && c counts as ONE run for cognitive.
	 * Cognitive: 1+0 (if) + 1 (one && run) = 2.
	 */
	@Test
	void logical_operator_run_cognitive() {
		assertEquals(2, ComplexityCalculator.computeCognitive(parseMethod(LOGICAL_RUN_METHOD)));
	}

	/**
	 * Cognitive: if (+1), else-if (+1), and the {@code &&} run in the else-if
	 * condition (+1) = 3. The condition's operators add no nesting increment.
	 */
	@Test
	void logical_operator_run_in_else_if_condition_cognitive() {
		MethodDeclaration m = parseMethod("""
				public String f(boolean a, boolean b, boolean c, boolean d) {
				    if (a) {
				        return "x";
				    } else if (b && c && d) {
				        return "y";
				    }
				    return "z";
				}
				""");
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * Mixed operators: {@code a && b || c} is an {@code &&} run and an {@code ||}
	 * run. Cognitive: if (+1) + 2 = 3.
	 */
	@Test
	void mixed_logical_operators_in_if_condition_cognitive() {
		MethodDeclaration m = parseMethod("""
				public boolean f(boolean a, boolean b, boolean c) {
				    if (a && b || c) {
				        return true;
				    }
				    return false;
				}
				""");
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * The cognitive complexity specification's own example: {@code a && b && c ||
	 * d || e && f} is an {@code &&} run, an {@code ||} run and a second {@code &&}
	 * run = 3, outside any if.
	 */
	@Test
	void logical_operator_runs_follow_the_specification_example() {
		MethodDeclaration m = parseMethod("""
				public boolean f(boolean a, boolean b, boolean c, boolean d, boolean e, boolean f) {
				    return a && b && c || d || e && f;
				}
				""");
		assertEquals(3, ComplexityCalculator.computeCognitive(m));
	}

	/**
	 * Body lines holding a code token: the brace line, {@code int x = 1;} and the
	 * closing brace = 3. The two comment-only lines are not counted.
	 */
	@Test
	void method_loc_excludes_comment_only_lines() {
		MethodDeclaration m = parseMethod("""
				public void fiveLines() {
				    // line 2
				    int x = 1;
				    // line 4
				}
				""");
		assertEquals(3, ComplexityCalculator.computeMethodLoc(m));
	}

	/**
	 * Annotations, a two-line signature, blank lines and comment-only lines.
	 * Counted: the line that ends the signature and opens the body (1), {@code int
	 * s = a + b;} (2), {@code return s;} (3), the closing brace (4) = 4. Not
	 * counted: the two annotation lines, the first two signature lines, the blank
	 * lines, the line comment and the two lines of the block comment.
	 */
	@Test
	void method_loc_counts_only_body_lines_with_code() {
		MethodDeclaration m = parseMethod("""
				@Override
				@Deprecated
				public int compute(
				        int a,
				        int b) {
				    // comment only

				    int s = a + b; // a trailing comment does not change the line

				    /* block
				       comment */
				    return s;
				}
				""");
		assertEquals(4, ComplexityCalculator.computeMethodLoc(m));
	}

	/**
	 * Same rule for a constructor: brace line (1), {@code this.a = a;} (2),
	 * {@code this.b = b;} (3), closing brace (4) = 4. The second signature line,
	 * the blank line and the comment-only line are not counted.
	 */
	@Test
	void constructor_loc_counts_only_body_lines_with_code() {
		ConstructorDeclaration c = parseConstructor("""
				public _Wrap_(int a,
				              int b) {

				    // set up
				    this.a = a;
				    this.b = b;
				}
				""");
		assertEquals(4, ComplexityCalculator.computeMethodLoc(c));
	}

	/** A body written on one line counts 1: the line holds code tokens. */
	@Test
	void method_loc_single_line_body_is_one() {
		MethodDeclaration m = parseMethod("int f() { return x; }");
		assertEquals(1, ComplexityCalculator.computeMethodLoc(m));
	}

	@Test
	void method_loc_text_block_counts_lines_that_start_a_token() {
		// Line 1 brace, line 2 starts the text block, line 3 is inside it (no token
		// starts there), line 4 holds the {@code ;} token, line 5 the closing brace.
		MethodDeclaration m = parseMethod("""
				String f() {
				    return \"\"\"
				        a
				        b\"\"\";
				}
				""");
		assertEquals(4, ComplexityCalculator.computeMethodLoc(m));
	}

	/**
	 * WMC = sum of cyclomatic complexities. Two methods: cc=1, cc=2 → WMC = 3.
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
		assertEquals(3, env.getInt("wmc"));
	}

	/**
	 * CBO counts distinct non-trivial types. OwnerRepository + Owner are domain
	 * types; String/List/Long excluded. Expected CBO = 2.
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
		assertEquals(2, env.getInt("cbo")); // OwnerRepository + Owner
	}

	/**
	 * A type that appears only as a locally declared variable counts: Owner = 1.
	 * String is a staple the per-file count leaves out; a {@code var} variable and
	 * the primitive name no class. {@code referenced_types} filters nothing but
	 * those: it keeps String, and the graph stage decides what the JDK is.
	 */
	@Test
	void cbo_counts_local_variable_types() {
		JSONObject env = parse("""
				package com.example;
				public class OwnerReport {
				    public void run() {
				        Owner owner = null;
				        String label = "x";
				        var inferred = label;
				        int count = 0;
				    }
				}
				""");
		assertEquals(1, env.getInt("cbo"));
		assertEquals(List.of("Owner", "String"), referencedTypes(env));
	}

	/**
	 * A type that appears only in a throws clause counts: OwnerNotFoundException =
	 * 1, on a method and on a constructor (ConfigError = 2). {@code Exception} is a
	 * java.lang class: the per-file count leaves it out, {@code referenced_types}
	 * keeps it for the graph stage to drop.
	 */
	@Test
	void cbo_counts_throws_types() {
		JSONObject env = parse("""
				package com.example;
				public class OwnerLoader {
				    public OwnerLoader() throws ConfigError {}
				    public void load() throws OwnerNotFoundException, Exception {}
				}
				""");
		assertEquals(2, env.getInt("cbo"));
		assertEquals(List.of("ConfigError", "Exception", "OwnerNotFoundException"), referencedTypes(env));
	}

	/**
	 * The same type named in several places counts once; arrays count as the
	 * element type.
	 */
	@Test
	void cbo_counts_a_repeated_type_once() {
		JSONObject env = parse("""
				package com.example;
				public class Shelf {
				    private Owner[] owners;
				    public Owner first() { Owner o = null; return o; }
				    public void put(Owner o) throws Owner {}
				}
				""");
		assertEquals(1, env.getInt("cbo"));
	}

	/**
	 * A type counts every class it names: type arguments recursively, wildcard
	 * bounds, and array element types. The per-file count leaves out the staples
	 * (Map, String, List, Set): Pet, Owner and Vet remain = 3.
	 */
	@Test
	void cbo_counts_classes_named_in_type_arguments() {
		JSONObject env = parse("""
				package com.example;
				public class Clinic {
				    private Map<String, List<Pet>> index;
				    private Set<? extends Owner> owners;
				    private List<? super Vet> sink;
				    private Pet[][] grid;
				}
				""");
		assertEquals(List.of("List", "Map", "Owner", "Pet", "Set", "String", "Vet"), referencedTypes(env));
		assertEquals(3, env.getInt("cbo"));
	}

	/**
	 * Type arguments count in a return type, a parameter, a local and a throws
	 * clause.
	 */
	@Test
	void type_arguments_count_in_every_source() {
		JSONObject env = parse("""
				package com.example;
				public class Clinic {
				    public List<Pet> pets(Optional<Owner> owner) throws Failure<Vet> {
				        Map<String, Visit> visits = null;
				        return null;
				    }
				}
				""");
		assertEquals(List.of("Failure", "List", "Map", "Optional", "Owner", "Pet", "String", "Vet", "Visit"),
				referencedTypes(env));
	}

	/**
	 * A class's own type parameter and a generic method's or constructor's are not
	 * classes: as a field, a return, a local, a parameter and in throws, T and E
	 * leave only the real classes behind.
	 */
	@Test
	void type_parameters_are_not_counted() {
		JSONObject env = parse("""
				package com.example;
				public class Repo<T> {
				    private T value;
				    private List<T> items;
				    public <C> Repo(C seed) throws C { }
				    public T find(Long id) { T found = null; return found; }
				    public <E extends Exception> void check(E problem) throws E { E again = problem; }
				}
				""");
		assertEquals(List.of("List", "Long"), referencedTypes(env));
	}

	/**
	 * A type parameter shadows a class only where it is in scope: the {@code T} of
	 * one method does not hide a class named T used by another.
	 */
	@Test
	void a_type_parameter_hides_a_name_only_in_its_own_scope() {
		JSONObject env = parse("""
				package com.example;
				public class Mixed {
				    public <T> void generic(T item) { }
				    public void plain(T item) { }
				}
				""");
		assertEquals(List.of("T"), referencedTypes(env));
	}

	/**
	 * A type the class declares itself, written without its outer type, is reported
	 * qualified with the class's name so the graph stage can recognise it as the
	 * class itself; written qualified it is left as it is. The per-file count does
	 * not count it either.
	 */
	@Test
	void own_nested_types_are_reported_qualified_with_the_outer_name() {
		JSONObject env = parse("""
				package com.example;
				public class OrderService {
				    private Helper helper;
				    public Node first() { Helper local = null; Deep d = null; Helper.Deep e = null; return null; }
				    static class Helper { class Deep { } }
				    class Node { }
				}
				""");
		assertEquals(
				List.of("OrderService.Deep", "OrderService.Helper", "OrderService.Helper.Deep", "OrderService.Node"),
				referencedTypes(env));
		assertEquals(0, env.getInt("cbo"));
	}

	/**
	 * The whole declaration is read, nested members included, and every kind of
	 * local variable counts: a nested class's field, a parameter and its throws
	 * clause, a catch parameter, a pattern variable and a lambda parameter with a
	 * written type.
	 */
	@Test
	void references_are_collected_from_the_whole_declaration() {
		JSONObject env = parse("""
				package com.example;
				public class Outer {
				    static class Inner {
				        private Alpha alpha;
				        void work(Beta beta) throws Gamma {
				            try { run(); } catch (Delta | Epsilon failure) { }
				            Runnable r = new Runnable() { Zeta zeta; public void run() { Eta eta = null; } };
				        }
				    }
				    void test(Object o) {
				        if (o instanceof Theta theta) { }
				        java.util.function.Function<Iota, Kappa> f = (Iota i) -> null;
				    }
				}
				""");
		assertEquals(List.of("Alpha", "Beta", "Delta", "Epsilon", "Eta", "Gamma", "Iota", "Kappa", "Object", "Runnable",
				"Theta", "Zeta", "java.util.function.Function"), referencedTypes(env));
	}

	/**
	 * Switch statement — each non-default case label adds 1 to cyclomatic. Two case
	 * labels (1, 2) → CC = 1 + 2 = 3.
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
		assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
	}

	// -------------------------------------------------------------------------
	// Helpers
	// -------------------------------------------------------------------------

	private static JSONObject parse(String source) {
		CompilationUnit cu = StaticJavaParser.parse(source);
		return ParsedFileAssembler.buildEnvelope(cu, "test/Test.java");
	}

	private static List<String> referencedTypes(JSONObject env) {
		List<String> names = new ArrayList<>();
		env.getJSONArray("referenced_types").forEach(n -> names.add((String) n));
		return names;
	}

	private static ConstructorDeclaration parseConstructor(String ctorSource) {
		String wrapped = "class _Wrap_ { " + ctorSource + " }";
		CompilationUnit cu = StaticJavaParser.parse(wrapped);
		return cu.getClassByName("_Wrap_").orElseThrow(() -> new IllegalStateException("wrapper class not found"))
				.getConstructors().get(0);
	}

	private static MethodDeclaration parseMethod(String methodSource) {
		String wrapped = "class _Wrap_ { " + methodSource + " }";
		CompilationUnit cu = StaticJavaParser.parse(wrapped);
		ClassOrInterfaceDeclaration cls = cu.getClassByName("_Wrap_")
				.orElseThrow(() -> new IllegalStateException("wrapper class not found"));
		return cls.getMethods().get(0);
	}
}
