import time

from codeograph.evals.scorecard_schema import BooleanThreshold, CheckResult
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_golden_graph_agreement(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    # TODO: learner to implement exact value computation for golden_graph_agreement
    # current graph.json canonical-form sha256 matches tests/goldens/<corpus_id>/graph.json
    value: bool = True

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="golden_graph_agreement",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale="FR-7a / ADR-007 — golden_graph_agreement ensures the emitted graph matches the committed fixture exactly (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={"notes": "Not yet fully implemented"},
    )
