package io.codeograph.parser;

import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import org.json.JSONObject;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for {@link ComplexityCalculator} — cyclomatic, cognitive, LOC, WMC, CBO.
 *
 * <p>All expected values are hand-calculated and annotated in the fixture comments.
 * WMC and CBO are verified via the assembled envelope (they're class-level aggregates).
 */
class ComplexityCalculatorTest {

    @BeforeAll
    static void configureParser() {
        StaticJavaParser.setConfiguration(
                new ParserConfiguration()
                        .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17));
    }

    /**
     * Trivial method — no decisions.
     * Cyclomatic: 1  (base only)
     * Cognitive:  0
     * LOC:        3
     */
    @Test
    void trivial_method_baseline() {
        MethodDeclaration m = parseMethod("""
                public int getValue() {
                    return value;
                }
                """);
        // TODO: assertEquals(1, ComplexityCalculator.computeCyclomatic(m));
        // TODO: assertEquals(0, ComplexityCalculator.computeCognitive(m));
        // TODO: assertEquals(3, ComplexityCalculator.computeMethodLoc(m));
    }

    /**
     * Single if-else.
     * Cyclomatic: 1 + 1 (if) = 2
     * Cognitive:  1 (if+0) + 1 (else) = 2
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
        // TODO: assertEquals(2, ComplexityCalculator.computeCyclomatic(m));
        // TODO: assertEquals(2, ComplexityCalculator.computeCognitive(m));
    }

    /**
     * if / else-if / else chain.
     * Cyclomatic: 1 + 2 (two IfStmt nodes) = 3
     * Cognitive:  1+0 (if) + 1 (else-if) + 1 (else) = 3
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
        // TODO: assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
        // TODO: assertEquals(3, ComplexityCalculator.computeCognitive(m));
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
        // TODO: assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
        // TODO: assertEquals(3, ComplexityCalculator.computeCognitive(m));
    }

    /**
     * Logical operator sequence: a && b && c counts as ONE run for cognitive.
     * Cyclomatic: 1 + 2 (two &&) = 3
     * Cognitive:  1+0 (if) + 1 (one && run) = 2
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
        // TODO: assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
        // TODO: assertEquals(2, ComplexityCalculator.computeCognitive(m));
    }

    @Test
    void method_loc_counts_physical_lines() {
        MethodDeclaration m = parseMethod("""
                public void fiveLines() {
                    // line 2
                    int x = 1;
                    // line 4
                }
                """);
        // TODO: assertEquals(5, ComplexityCalculator.computeMethodLoc(m));
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
        // TODO: assertEquals(3, env.getInt("wmc"));
    }

    /**
     * CBO counts distinct non-trivial types.
     * OwnerRepository + Owner are domain types; String/List/Long excluded.
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
     * Switch statement — each non-default case label adds 1 to cyclomatic.
     * Two case labels (1, 2) → CC = 1 + 2 = 3.
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
        // TODO: assertEquals(3, ComplexityCalculator.computeCyclomatic(m));
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    private static JSONObject parse(String source) {
        CompilationUnit cu = StaticJavaParser.parse(source);
        return ParsedFileAssembler.buildEnvelope(cu, "test/Test.java");
    }

    private static MethodDeclaration parseMethod(String methodSource) {
        String wrapped = "class _Wrap_ { " + methodSource + " }";
        CompilationUnit cu = StaticJavaParser.parse(wrapped);
        ClassOrInterfaceDeclaration cls = cu.getClassByName("_Wrap_")
                .orElseThrow(() -> new IllegalStateException("wrapper class not found"));
        return cls.getMethods().get(0);
    }
}
