package io.codeograph.parser;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.ConditionalExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.stmt.*;

import java.util.HashSet;
import java.util.Set;

/**
 * Complexity metrics for Java methods and classes.
 *
 * <p>
 * All methods are stateless and thread-safe. Inputs are JavaParser AST nodes;
 * no JSON I/O occurs here.
 *
 * <p>
 * Metrics implemented:
 * <ul>
 * <li>Cyclomatic complexity — McCabe (1976), IEEE TSE 2(4), 308–320.</li>
 * <li>Cognitive complexity — Campbell / SonarSource (2018) white paper.</li>
 * <li>Method LOC — physical line count (begin to end inclusive).</li>
 * <li>CBO — Chidamber & Kemerer (1994), IEEE TSE 20(6), 476–493.</li>
 * </ul>
 */
final class ComplexityCalculator {

	private ComplexityCalculator() {
	}

	// -------------------------------------------------------------------------
	// Cyclomatic complexity
	// -------------------------------------------------------------------------

	/**
	 * Cyclomatic complexity (McCabe 1976) for a method or constructor.
	 *
	 * V(G) = number of binary decisions + 1. Counts: if/else-if, for, enhanced-for,
	 * while, do-while, switch case labels, catch clauses, ternary expressions, and
	 * binary logical operators (&amp;&amp; / ||).
	 */
	static int computeCyclomatic(Node scope) {
		int cc = 1; // base: one unconditional execution path
		cc += scope.findAll(IfStmt.class).size();
		cc += scope.findAll(ForStmt.class).size();
		cc += scope.findAll(ForEachStmt.class).size();
		cc += scope.findAll(WhileStmt.class).size();
		cc += scope.findAll(DoStmt.class).size();
		cc += scope.findAll(CatchClause.class).size();
		cc += scope.findAll(ConditionalExpr.class).size();
		cc += scope.findAll(SwitchEntry.class).stream().filter(e -> !e.getLabels().isEmpty()).count();
		cc += scope.findAll(BinaryExpr.class).stream()
				.filter(e -> e.getOperator() == BinaryExpr.Operator.AND || e.getOperator() == BinaryExpr.Operator.OR)
				.count();
		return cc;
	}

	// -------------------------------------------------------------------------
	// Cognitive complexity
	// -------------------------------------------------------------------------

	/**
	 * Cognitive complexity (Campbell / SonarSource 2018) for a method.
	 *
	 * Structural increments penalise nesting depth; logical operator sequences are
	 * counted as a unit rather than per operator.
	 */
	static int computeCognitive(MethodDeclaration method) {
		int[] acc = {0};
		method.getBody().ifPresent(body -> traverseCognitive(body, 0, acc));
		return acc[0];
	}

	/** Overload for constructors (body is never absent). */
	static int computeCognitive(ConstructorDeclaration ctor) {
		int[] acc = {0};
		traverseCognitive(ctor.getBody(), 0, acc);
		return acc[0];
	}

	/**
	 * Recursive AST traversal for cognitive complexity.
	 *
	 * Nesting-incrementing structures (if/for/while/do/switch/catch/lambda) each
	 * add (1 + current depth). else and else-if add 1 only (no nesting increment
	 * per spec §1.3). Logical operator sequences count as 1 per contiguous run of
	 * the same operator.
	 */
	private static void traverseCognitive(Node node, int depth, int[] acc) {
		for (Node child : node.getChildNodes()) {
			if (child instanceof IfStmt ifStmt) {
				handleIfChain(ifStmt, depth, acc);

			} else if (child instanceof ForStmt || child instanceof ForEachStmt || child instanceof WhileStmt
					|| child instanceof DoStmt || child instanceof SwitchStmt) {
				acc[0] += 1 + depth;
				traverseCognitive(child, depth + 1, acc);

			} else if (child instanceof CatchClause) {
				acc[0] += 1 + depth;
				traverseCognitive(child, depth + 1, acc);

			} else if (child instanceof LambdaExpr) {
				acc[0] += 1;
				traverseCognitive(child, depth + 1, acc);

			} else if (child instanceof BinaryExpr bExpr) {
				BinaryExpr.Operator op = bExpr.getOperator();
				if (op == BinaryExpr.Operator.AND || op == BinaryExpr.Operator.OR) {
					// Count only the root of a same-operator run (not each operator in a && b && c)
					boolean isRunRoot = !(bExpr.getParentNode().orElse(null) instanceof BinaryExpr parent
							&& parent.getOperator() == op);
					if (isRunRoot)
						acc[0] += 1;
				}
				traverseCognitive(child, depth, acc);

			} else {
				traverseCognitive(child, depth, acc);
			}
		}
	}

	/**
	 * Walk an if / else-if / else chain applying the SonarSource rule: if: +1 +
	 * nesting_depth (structural + nesting increment) else-if: +1 (structural only —
	 * no nesting increment) else: +1 (structural only — no nesting increment)
	 */
	private static void handleIfChain(IfStmt root, int depth, int[] acc) {
		boolean first = true;
		Statement current = root;

		while (current instanceof IfStmt curIf) {
			acc[0] += first ? (1 + depth) : 1;
			first = false;
			traverseCognitive(curIf.getThenStmt(), depth + 1, acc);
			if (curIf.getElseStmt().isEmpty())
				break;
			current = curIf.getElseStmt().get();
		}

		if (!(current instanceof IfStmt)) {
			acc[0] += 1;
			traverseCognitive(current, depth + 1, acc);
		}
	}

	// -------------------------------------------------------------------------
	// Method LOC
	// -------------------------------------------------------------------------

	/**
	 * Physical lines of code for a method (begin to end inclusive). Includes blank
	 * lines and comments — coarse size proxy.
	 */
	static int computeMethodLoc(MethodDeclaration method) {
		return method.getRange().map(r -> r.end.line - r.begin.line + 1).orElse(0);
	}

	/** Overload for constructors. */
	static int computeMethodLoc(ConstructorDeclaration ctor) {
		return ctor.getRange().map(r -> r.end.line - r.begin.line + 1).orElse(0);
	}

	// -------------------------------------------------------------------------
	// CBO
	// -------------------------------------------------------------------------

	/**
	 * CBO (Coupling Between Objects) — count of distinct non-trivial type names
	 * referenced in field declarations, method parameters, and method return types.
	 *
	 * Generics are stripped to the outer type name (e.g. List&lt;User&gt; → List,
	 * then excluded as a container type). Primitives and java.lang/java.util
	 * staples are excluded via {@link ParserConstants#CBO_EXCLUDED_TYPES}.
	 */
	static int computeCbo(ClassOrInterfaceDeclaration decl) {
		Set<String> types = new HashSet<>();

		decl.getFields().forEach(f -> types.add(stripGenerics(f.getElementType().asString())));

		decl.getMethods().forEach(m -> {
			types.add(stripGenerics(m.getTypeAsString()));
			m.getParameters().forEach(p -> types.add(stripGenerics(p.getType().asString())));
		});

		decl.getConstructors()
				.forEach(c -> c.getParameters().forEach(p -> types.add(stripGenerics(p.getType().asString()))));

		types.removeIf(t -> t.isBlank() || ParserConstants.CBO_EXCLUDED_TYPES.contains(t));
		return types.size();
	}

	/** Strip generic type parameters: "List&lt;User&gt;" → "List". */
	private static String stripGenerics(String type) {
		int idx = type.indexOf('<');
		return (idx >= 0 ? type.substring(0, idx) : type).trim();
	}
}
