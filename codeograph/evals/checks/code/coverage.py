import json
import time
from pathlib import Path
from typing import Any

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold

_RATIONALE = (
    "ADR-010 Fork 9 coverage matrix defines what v1 promises to translate. "
    "The 95% sharp-pass bar holds the tool to its own published matrix; "
    "the 85% floor catches systemic regressions while the band signals a "
    "corpus with unusual annotation density needing human review (ADR-017 Fork 4)."
)

# Sidecar written by cli/render.py alongside compile-checks sidecar.
# Contains per-group SelectionResult extension fields (refused, stub_todos,
# feature_policies_active) needed to compute v1_actually_emitted / v1_translatable.
# Not yet written by the render CLI — this check skips until that step is added
# (tracked as a follow-up to M5 runner wiring, DC4).
_COVERAGE_SIDECAR_NAME = "coverage-data.{target}.json"


def check_coverage(output_dir: Path, target: str) -> CheckResult:
    """Compute feature coverage per ADR-017 Fork 4.

    Formula (ADR-010 Fork 9):
        v1_translatable     = Spring annotations encountered ∩ ADR-010 v1 matrix
        v1_actually_emitted = v1_translatable - refused - stub_todos
        value               = v1_actually_emitted / v1_translatable

    Reads from evals/coverage-data.<target>.json sidecar written by cli/render.py.
    Skips with no_v1_translatable_features_in_corpus when sidecar is absent
    (sidecar writing not yet wired — follow-up to M5 runner integration).
    """
    start_time = time.perf_counter()

    def _elapsed() -> int:
        return int((time.perf_counter() - start_time) * 1000)

    # ------------------------------------------------------------------ #
    # 1. Locate and read the coverage-data sidecar
    # ------------------------------------------------------------------ #
    sidecar_name = _COVERAGE_SIDECAR_NAME.format(target=target)
    sidecar_path = output_dir / "evals" / sidecar_name

    if not sidecar_path.exists():
        return CheckResult(
            id="coverage",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "no_v1_translatable_features_in_corpus",
                "note": (
                    f"Coverage sidecar {sidecar_name} not found in evals/. "
                    "This file is written by cli/render.py — wiring pending M5 runner integration."
                ),
            },
        )

    coverage_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    groups: list[dict[str, Any]] = coverage_data.get("groups", [])

    # ------------------------------------------------------------------ #
    # 2. Aggregate across all domain groups
    # ------------------------------------------------------------------ #
    total_selected = sum(len(g.get("selected", [])) for g in groups)
    total_refused = sum(len(g.get("refused", [])) for g in groups)
    total_stub_todos = sum(len(g.get("stub_todos", [])) for g in groups)

    # v1_translatable proxy: all selected classes (they were chosen because
    # they have v1-translatable features; refused/stubs reduce the numerator).
    v1_translatable = total_selected + total_refused  # selected + those refused by policy
    v1_actually_emitted = total_selected - total_stub_todos  # selected minus stub_todo classes

    # ------------------------------------------------------------------ #
    # 3. Guard: empty denominator
    # ------------------------------------------------------------------ #
    if v1_translatable == 0:
        return CheckResult(
            id="coverage",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "no_v1_translatable_features_in_corpus",
                "total_selected": total_selected,
                "total_refused": total_refused,
            },
        )

    value = max(0.0, v1_actually_emitted / v1_translatable)

    policies: list[str] = []
    for g in groups:
        policies.extend(g.get("feature_policies_active", []))

    return CheckResult(
        id="coverage",
        category="code",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
        rationale=_RATIONALE,
        duration_ms=_elapsed(),
        details={
            "v1_translatable": v1_translatable,
            "v1_actually_emitted": v1_actually_emitted,
            "refused_count": total_refused,
            "stub_todo_count": total_stub_todos,
            "feature_policies_active": list(set(policies)),
            "groups": len(groups),
        },
    )
