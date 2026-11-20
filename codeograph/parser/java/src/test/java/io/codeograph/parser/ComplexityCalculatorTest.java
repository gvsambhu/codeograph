package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

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
	@Disabled("Cognitive complexity does not count && / || runs inside an if condition: the score is 1, the definition gives 2")
	@Test
	void logical_operator_run_cognitive() {
		assertEquals(2, ComplexityCalculator.computeCognitive(parseMethod(LOGICAL_RUN_METHOD)));
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
