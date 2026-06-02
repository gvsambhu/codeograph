import time
from pathlib import Path
from typing import Any

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold


def check_coverage(output_dir: Path, target: str) -> CheckResult:
    start_time = time.perf_counter()

    # TODO: Read the SelectionResult for this target (either from manifest.json or sidecar)
    # TODO: Calculate coverage: v1_actually_emitted / v1_translatable
    #       - Derive from SelectionResult.refused, stub_todos, feature_policies_active
    # TODO: If denominator is 0, return skip with details.skip_reason="no_v1_translatable_features_in_corpus"
    value: float = 0.0

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="coverage",
        category="code",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
        rationale="ADR-010 Fork 9 coverage matrix defines what v1 promises to translate. The 95% sharp-pass bar holds the tool to its own published matrix; the 85% floor catches systemic regressions while the band signals a corpus with unusual annotation density needing human review (ADR-017 Fork 4).",
        duration_ms=duration_ms,
        details={"notes": "Not yet fully implemented"},
    )
