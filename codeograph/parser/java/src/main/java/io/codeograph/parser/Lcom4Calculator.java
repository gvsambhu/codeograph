package io.codeograph.parser;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * LCOM4 (Lack of Cohesion of Methods 4) calculator.
 *
 * <p>
 * Graph definition (Hitz &amp; Montazeri 1995):
 * <ul>
 * <li>Nodes = all non-static methods and constructors in the class.</li>
 * <li>Edges = an edge between M_i and M_j when:
 * <ul>
 * <li>(a) they share at least one accessed field, OR</li>
 * <li>(b) one directly calls the other (unscoped or this. call).</li>
 * </ul>
 * </li>
 * <li>LCOM4 = number of weakly connected components. 1 = fully cohesive.</li>
 * </ul>
 *
 * <p>
 * Operates entirely on finished JSON arrays — no AST access required (Option
 * B). Each method entry must carry {@code accessed_fields}, {@code calls},
 * {@code modifiers}, and {@code name} keys (populated by
 * {@link ParsedFileAssembler}).
 *
 * <p>
 * Reference: Hitz, M. &amp; Montazeri, B. (1995). "Measuring Coupling and
 * Cohesion In Object-Oriented Systems." Proc. Int. Symp. Applied Corporate
 * Computing.
 */
final class Lcom4Calculator {

	private Lcom4Calculator() {
	}

	/**
	 * Compute LCOM4 for a class given its methods array.
	 *
	 * @param methodsArr
	 *            JSON array where each element is a method/constructor fact
	 * @return number of weakly connected components (&gt;= 1)
	 */
	static int computeLcom4(JSONArray methodsArr) {

		// --- Step 1: collect non-static methods ---
		// Static methods are excluded: they don't participate in instance cohesion.
		List<JSONObject> methods = new ArrayList<>();
		for (int i = 0; i < methodsArr.length(); i++) {
			JSONObject m = methodsArr.getJSONObject(i);
			JSONArray mods = m.optJSONArray("modifiers");
			boolean isStatic = false;
			if (mods != null) {
				for (int k = 0; k < mods.length(); k++) {
					if ("static".equals(mods.getString(k))) {
						isStatic = true;
						break;
					}
				}
			}
			if (!isStatic)
				methods.add(m);
		}

		int n = methods.size();
		if (n <= 1)
			return 1;

		// --- Step 2: build adjacency list ---
		// adj.get(i) holds the set of node indices directly connected to i.
		// Using Set<Integer> per node avoids duplicate edges from the pair loop.
		List<Set<Integer>> adj = new ArrayList<>(n);
		for (int i = 0; i < n; i++)
			adj.add(new HashSet<>());

		for (int i = 0; i < n; i++) {
			JSONArray fieldsI = methods.get(i).optJSONArray("accessed_fields");
			JSONArray callsI = methods.get(i).optJSONArray("calls");
			String nameI = methods.get(i).optString("name");

			Set<String> fieldsISet = new HashSet<>();
			for (int j = 0; j < fieldsI.length(); j++) {
				fieldsISet.add(fieldsI.getString(j));
			}

			Set<String> calleesI = new HashSet<>();
			for (int j = 0; j < callsI.length(); j++) {
				calleesI.add(extractCalleeName(callsI.getString(j)));
			}

			for (int j = i + 1; j < n; j++) {
				JSONArray fieldsJ = methods.get(j).optJSONArray("accessed_fields");
				JSONArray callsJ = methods.get(j).optJSONArray("calls");
				String nameJ = methods.get(j).optString("name");

				Set<String> calleesJ = new HashSet<>();
				for (int k = 0; k < callsJ.length(); k++) {
					calleesJ.add(extractCalleeName(callsJ.getString(k)));
				}

				// (a) Shared-field edge
				boolean found = false;
				for (int k = 0; k < fieldsJ.length(); k++) {
					if (fieldsISet.contains(fieldsJ.getString(k))) {
						adj.get(i).add(j);
						adj.get(j).add(i);
						found = true;
						break;
					}
				}

				// (b) Direct-call edge
				if (!found && (calleesI.contains(nameJ) || calleesJ.contains(nameI))) {
					adj.get(i).add(j);
					adj.get(j).add(i);
				}
			}
		}

		// --- Step 3: count connected components ---
		return countComponents(adj, n);
	}

	/**
	 * Count weakly connected components using union-by-size on an adjacency list.
	 *
	 * <p>
	 * Each node starts in its own component set. For every edge (i, j), the smaller
	 * component is merged into the larger one (union by size); all nodes in the
	 * absorbed set have their map entry updated to the surviving set. Total merge
	 * work is O(n log n); traversal is O(n + E).
	 *
	 * <p>
	 * Contract: returns &gt;= 1. Caller guarantees {@code n >= 2}.
	 *
	 * @param adj
	 *            adjacency list — {@code adj.get(i)} is the set of neighbors of i
	 * @param n
	 *            number of nodes
	 * @return number of connected components (LCOM4 value)
	 */
	static int countComponents(List<Set<Integer>> adj, int n) {
		@SuppressWarnings("unchecked")
		Set<Integer>[] nodeToComponent = new Set[n];
		for (int i = 0; i < n; i++) {
			Set<Integer> s = new HashSet<>();
			s.add(i);
			nodeToComponent[i] = s;
		}

		for (int i = 0; i < n; i++) {
			for (int j : adj.get(i)) {
				Set<Integer> ci = nodeToComponent[i];
				Set<Integer> cj = nodeToComponent[j];
				if (ci == cj)
					continue;

				Set<Integer> bigger = ci.size() >= cj.size() ? ci : cj;
				Set<Integer> smaller = ci.size() >= cj.size() ? cj : ci;

				bigger.addAll(smaller);
				for (int node : smaller) {
					nodeToComponent[node] = bigger;
				}
			}
		}

		return (int) Arrays.stream(nodeToComponent).distinct().count();
	}

	/**
	 * Extract the simple callee name from a raw
	 * {@link com.github.javaparser.ast.expr.MethodCallExpr#toString()} string.
	 *
	 * <pre>
	 *   "clean()"                → "clean"
	 *   "this.save(user)"        → "save"
	 *   "ownerRepo.findById(id)" → "findById"
	 * </pre>
	 *
	 * Cross-object calls yield only the method name, so a false-positive edge is
	 * possible when the class declares a method with the same name. Acceptable for
	 * v1 name-based LCOM4 without a symbol solver.
	 */
	static String extractCalleeName(String call) {
		int parenIdx = call.indexOf('(');
		if (parenIdx < 0)
			return call;
		int dotIdx = call.lastIndexOf('.', parenIdx);
		return call.substring(dotIdx + 1, parenIdx);
	}
}
