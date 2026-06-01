import time

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold


def check_compile() -> CheckResult:
    start_time = time.perf_counter()

    # TODO: learner to implement exact value computation for compile check
    # Aggregates ADR-008's CompileCheck list per Fork 6's execution policy.
    value: float = 0.0

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="compile",
        category="code",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="FR-7 — compile is the minimum bar for generated code; ADR-008 Fork 3 supplies the per-renderer check list; aggregation is sharp because any failure indicates a renderer bug (ADR-017 Fork 4).",
        duration_ms=duration_ms,
        details={"notes": "Not yet fully implemented"},
    )
