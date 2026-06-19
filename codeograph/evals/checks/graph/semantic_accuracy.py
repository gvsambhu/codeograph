import time

from codeograph.evals.models import CheckResult, ScoreBandThreshold
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_semantic_accuracy(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # Deferred to ADR-020 (LLM-judge calibration, v1.1)
    return CheckResult(
        id="semantic_accuracy",
        category="graph",
        result="skip",
        value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="Deferred to ADR-020 (LLM-judge calibration, v1.1).",
        duration_ms=duration_ms,
        details={"skip_reason": "deferred_v1.1", "owner_adr": "ADR-020"},
    )
