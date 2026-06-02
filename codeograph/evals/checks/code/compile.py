import time
from pathlib import Path
from typing import Any

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold


def check_compile(output_dir: Path, target: str) -> CheckResult:
    start_time = time.perf_counter()

    # TODO: Read evals/compile-checks.<target>.json (via manifest pointer & verify sha256)
    # TODO: Execute each command sequentially for this target per Fork 6 policy:
    #       - Preflight shutil.which to ensure tool exists
    #       - Enforce 120s timeout per command (subprocess.run with timeout)
    #       - Capture stdout/stderr and write full logs to `evals/<target>-scorecard.compile.<name>.log`
    #       - Capture the last 100 lines (tail) of stdout/stderr for CheckResult.details
    # TODO: Aggregate pass/fail ratio for the final `value`
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
