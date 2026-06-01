import time

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_relationship_correctness(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    valid_node_ids = {node.root.id for node in graph.nodes}

    total_edges = 0
    unresolved_call_edges = 0
    resolved_edges = 0

    for edge_wrapper in graph.edges:
        edge = edge_wrapper.root
        total_edges += 1

        if edge.kind == "calls_unresolved":
            unresolved_call_edges += 1
        else:
            if edge.source in valid_node_ids and edge.target in valid_node_ids:
                resolved_edges += 1

    denominator = total_edges - unresolved_call_edges
    value: float = (resolved_edges / denominator) if denominator > 0 else 1.0

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="relationship_correctness",
        category="graph",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="FR-7a — relationship_correctness ensures all resolvable calls are correctly mapped to valid edges (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={
            "total_edges": total_edges,
            "unresolved_call_edges": unresolved_call_edges,
            "resolved_edges": resolved_edges,
        },
    )
