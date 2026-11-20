import time
from collections import defaultdict

from codeograph.evals.models import CheckResult, MaxCountThreshold
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_internal_consistency(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()
    violations: list[str] = []

    # (a) node id uniqueness within kind
    id_by_kind: dict[str, set[str]] = defaultdict(set)
    for node in graph.nodes:
        n = node.root
        if n.id in id_by_kind[n.kind]:
            violations.append(f"Duplicate node id '{n.id}' in kind '{n.kind}'")
        id_by_kind[n.kind].add(n.id)

    # (b) class references valid package (class id contains package part)
    for node in graph.nodes:
        n = node.root
        if n.kind == "class":
            parts = n.id.split(".")
            if len(parts) < 2:
                violations.append(f"Class node '{n.id}' does not reference a valid package")

    # (c) method's parent class exists
    class_ids = {
        node.root.id
        for node in graph.nodes
        if node.root.kind in ("class", "interface", "enum", "record", "annotation_type")
    }
    for node in graph.nodes:
        n = node.root
        if n.kind == "method":
            parent_fqcn = n.id.split("#")[0]
            if parent_fqcn not in class_ids:
                violations.append(f"Method '{n.id}' parent class '{parent_fqcn}' does not exist in graph")

    # unresolved_call edges carry an origin and a target
    for edge in graph.edges:
        e = edge.root
        if e.kind == "calls_unresolved":
            if not e.source or not e.target:
                violations.append(f"Unresolved call edge from '{e.source}' to '{e.target}' is missing origin or target")

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="internal_consistency",
        category="graph",
        value=len(violations),
        threshold=MaxCountThreshold(pass_at_or_below=0),
        rationale="FR-7a / ADR-032 — internal_consistency enforces four of ADR-032 Fork 3's five rules; the annotation-key rule is not yet run.",
        duration_ms=duration_ms,
        details={"violations": violations},
    )
