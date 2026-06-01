import time

from codeograph.evals.scorecard_schema import BooleanThreshold, CheckResult
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_reproducibility(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    # TODO: learner to implement exact value computation for reproducibility
    # rerun `codeograph run --ast-only` against the recorded source path three times; compare canonical-form sha256 of each run's graph.json
    value: bool = True

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="reproducibility",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale="FR-7a / ADR-017 — reproducibility ensures AST parsing determinism by comparing canonical sha256 across runs (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={"notes": "Not yet fully implemented"},
    )
