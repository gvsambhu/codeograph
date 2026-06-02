import time
from pathlib import Path

from codeograph.evals.scorecard_schema import CheckResult, ScoreBandThreshold


def check_llm_judge(output_dir: Path, target: str) -> CheckResult:
    start_time = time.perf_counter()

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    # Deferred to ADR-020 (LLM-judge calibration, v1.1)
    return CheckResult(
        id="llm_judge",
        category="code",
        result="skip",
        value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="Deferred to ADR-020 (LLM-judge calibration, v1.1).",
        duration_ms=duration_ms,
        details={"skip_reason": "deferred_v1.1", "owner_adr": "ADR-020"},
    )
