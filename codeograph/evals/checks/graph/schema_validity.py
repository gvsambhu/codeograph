import time

from codeograph.evals.scorecard_schema import BooleanThreshold, CheckResult
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph


def check_schema_validity(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    # TODO: learner to implement exact value computation for schema_validity
    # graph.json validates against evals/graph-schema.json
    value: bool = True

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="schema_validity",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale="FR-7a — schema_validity ensures the emitted graph.json strictly matches the Pydantic schema (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={"notes": "Not yet fully implemented"},
    )
