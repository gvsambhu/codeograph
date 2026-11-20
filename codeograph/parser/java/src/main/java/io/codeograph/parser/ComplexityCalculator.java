package io.codeograph.parser;

import com.github.javaparser.JavaToken;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.ConditionalExpr;
import com.github.javaparser.ast.expr.LambdaExpr;
import com.github.javaparser.ast.expr.PatternExpr;
import com.github.javaparser.ast.expr.VariableDeclarationExpr;
import com.github.javaparser.ast.nodeTypes.NodeWithTypeParameters;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.ast.type.IntersectionType;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.type.UnionType;
import com.github.javaparser.ast.type.WildcardType;
import com.github.javaparser.ast.stmt.*;

import java.util.HashSet;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;

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
 * <li>Method LOC — SonarSource S138: body lines holding a code token.</li>
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
	 * If, for, foreach, while, do, switch and catch each add (1 + current depth)
	 * and nest what they contain one level deeper. A lambda adds a flat 1 and nests
	 * its body one level deeper; the specification adds nothing for a lambda and
	 * only nests it. else and else-if add 1 only (no nesting increment per spec
	 * §1.3). Logical operator sequences count as 1 per contiguous run of the same
	 * operator, with no nesting increment, wherever they occur — an if or else-if
	 * condition included. The ternary operator and a break or continue to a label
	 * add nothing.
	 */
	private static void traverseCognitive(Node node, int depth, int[] acc) {
		for (Node child : node.getChildNodes()) {
			visitCognitive(child, depth, acc);
		}
	}

	/** Scores one node by the rules above, then descends into its children. */
	private static void visitCognitive(Node child, int depth, int[] acc) {
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
			// Operator runs in the condition add 1 each, with no nesting increment.
			visitCognitive(curIf.getCondition(), depth, acc);
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
	 * Method lines of code, counted as SonarSource rule S138 counts them: the
	 * distinct lines of the body block, its opening and closing brace lines
	 * included, that hold at least one code token. Blank lines and comment-only
	 * lines are not counted; the signature and annotations are not part of the
	 * body. A token spanning several lines (a text block) counts its first line.
	 */
	static int computeMethodLoc(MethodDeclaration method) {
		return method.getBody().map(ComplexityCalculator::countCodeLines).orElse(0);
	}

	/** Overload for constructors. */
	static int computeMethodLoc(ConstructorDeclaration ctor) {
		return countCodeLines(ctor.getBody());
	}

	/**
	 * Distinct begin lines of the block's tokens, skipping whitespace and comments.
	 */
	private static int countCodeLines(BlockStmt body) {
		Set<Integer> lines = new HashSet<>();
		body.getTokenRange().ifPresent(range -> {
			for (JavaToken token : range) {
				if (!token.getCategory().isWhitespaceOrComment()) {
					token.getRange().ifPresent(r -> lines.add(r.begin.line));
				}
			}
		});
		return lines.size();
	}

	// -------------------------------------------------------------------------
	// CBO
	// -------------------------------------------------------------------------

	/**
	 * CBO (Coupling Between Objects) as far as one file can tell — the names in
	 * {@code referenced} less the class itself, its own nested types and the
	 * {@link ParserConstants#CBO_EXCLUDED_TYPES} staples. The graph stage replaces
	 * it with the corpus-wide count, which also resolves the names, takes the JDK
	 * from the committed JDK list and adds call targets; this value stands where a
	 * class has no referenced types.
	 *
	 * @param referenced
	 *            the result of {@link #referencedTypes} for {@code decl}
	 */
	static int computeCbo(ClassOrInterfaceDeclaration decl, Set<String> referenced) {
		String self = decl.getNameAsString();
		return (int) referenced.stream().filter(t -> !t.isBlank() && !t.equals(self) && !t.startsWith(self + ".")
				&& !ParserConstants.CBO_EXCLUDED_TYPES.contains(t)).count();
	}

	/**
	 * Every class a declaration names, as written, in the places ADR-004 §3.4
	 * lists: field types, method and constructor return and parameter types,
	 * locally declared variable types (local variables, catch parameters, pattern
	 * variables, lambda parameters with a written type) and throws clauses. The
	 * whole declaration is read — nested, local and anonymous classes included —
	 * because a nested type is part of its outer class.
	 *
	 * <p>
	 * A type counts every class it names: {@code Map<String, List<Pet>>} gives
	 * {@code Map}, {@code String}, {@code List} and {@code Pet}; wildcard bounds
	 * and union (multi-catch) alternatives count, and an array counts by its
	 * element type. Primitives, {@code void} and {@code var} name no class. A name
	 * that is a type parameter in scope (a class's, a method's or a constructor's)
	 * is left out. A type the declaration itself declares, written without its
	 * outer type, is qualified with the declaration's name ({@code Helper} becomes
	 * {@code OrderService.Helper}), so the graph stage recognises it as the class
	 * itself.
	 *
	 * <p>
	 * Nothing is dropped as a JDK type here; that is decided on the graph side.
	 */
	static SortedSet<String> referencedTypes(ClassOrInterfaceDeclaration decl) {
		Set<String> ownTypes = new HashSet<>();
		decl.findAll(TypeDeclaration.class).forEach(t -> {
			if (t != decl)
				ownTypes.add(t.getNameAsString());
		});
		SortedSet<String> names = new TreeSet<>();
		String outer = decl.getNameAsString();

		decl.findAll(FieldDeclaration.class).forEach(f -> collect(f.getElementType(), outer, ownTypes, names));
		decl.findAll(MethodDeclaration.class).forEach(m -> {
			collect(m.getType(), outer, ownTypes, names);
			m.getThrownExceptions().forEach(t -> collect(t, outer, ownTypes, names));
		});
		decl.findAll(ConstructorDeclaration.class)
				.forEach(c -> c.getThrownExceptions().forEach(t -> collect(t, outer, ownTypes, names)));
		decl.findAll(Parameter.class).forEach(p -> collect(p.getType(), outer, ownTypes, names));
		decl.findAll(VariableDeclarationExpr.class).forEach(v -> collect(v.getElementType(), outer, ownTypes, names));
		decl.findAll(PatternExpr.class).forEach(p -> collect(p.getType(), outer, ownTypes, names));

		names.removeIf(String::isBlank);
		return names;
	}

	/** Adds each class {@code type} names, type arguments and bounds included. */
	private static void collect(Type type, String outer, Set<String> ownTypes, Set<String> out) {
		Type element = type.getElementType();
		if (element instanceof ClassOrInterfaceType named) {
			String written = named.getNameWithScope();
			int dot = written.indexOf('.');
			String first = dot < 0 ? written : written.substring(0, dot);
			if (dot >= 0 || !isTypeParameterInScope(named, first)) {
				out.add(ownTypes.contains(first) ? outer + "." + written : written);
			}
			named.getTypeArguments().ifPresent(args -> args.forEach(a -> collect(a, outer, ownTypes, out)));
		} else if (element instanceof WildcardType wildcard) {
			wildcard.getExtendedType().ifPresent(b -> collect(b, outer, ownTypes, out));
			wildcard.getSuperType().ifPresent(b -> collect(b, outer, ownTypes, out));
		} else if (element instanceof UnionType union) {
			union.getElements().forEach(a -> collect(a, outer, ownTypes, out));
		} else if (element instanceof IntersectionType intersection) {
			intersection.getElements().forEach(a -> collect(a, outer, ownTypes, out));
		}
	}

	/**
	 * True if an enclosing class, method or constructor declares a type parameter
	 * named {@code name}.
	 */
	private static boolean isTypeParameterInScope(Node from, String name) {
		for (Node n = from.getParentNode().orElse(null); n != null; n = n.getParentNode().orElse(null)) {
			if (n instanceof NodeWithTypeParameters<?> generic
					&& generic.getTypeParameters().stream().anyMatch(p -> p.getNameAsString().equals(name))) {
				return true;
			}
		}
		return false;
	}
}
