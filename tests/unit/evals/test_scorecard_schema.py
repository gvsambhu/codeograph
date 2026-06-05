"""Unit tests for codeograph/evals/scorecard_schema.py (ADR-017 Forks 1+2).

Covers:
- All four threshold kinds: BooleanThreshold, MinRatioThreshold,
  MaxCountThreshold, ScoreBandThreshold
- Mechanical result derivation per threshold (ADR-017 Fork 2 table)
- Band-gap → result "skip" with details.skip_reason == "band_gap"
- value=None → result "skip" (no threshold evaluation)
- Deferred-v1.1 skip pattern (ScoreBandThreshold with both nulls)
- JSON round-trip via model_dump / model_validate
- Scorecard envelope construction
"""

from __future__ import annotations

import pytest

from codeograph.evals.scorecard_schema import (
    BooleanThreshold,
    CheckResult,
    MaxCountThreshold,
    MinRatioThreshold,
    ScoreBandThreshold,
    Scorecard,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(
    threshold,
    value,
    *,
    result="skip",
    details=None,
) -> CheckResult:
    """Build a minimal CheckResult for threshold-derivation tests."""
    return CheckResult(
        id="test_check",
        category="graph",
        result=result,
        value=value,
        threshold=threshold,
        rationale="test",
        duration_ms=0,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# BooleanThreshold
# ---------------------------------------------------------------------------


class TestBooleanThreshold:
    def test_pass_when_value_matches_expected(self):
        r = _check(BooleanThreshold(expected=True), value=True)
        assert r.result == "pass"

    def test_fail_when_value_differs_from_expected(self):
        r = _check(BooleanThreshold(expected=True), value=False)
        assert r.result == "fail"

    def test_pass_with_false_expected(self):
        r = _check(BooleanThreshold(expected=False), value=False)
        assert r.result == "pass"

    def test_round_trip(self):
        t = BooleanThreshold(expected=True)
        assert BooleanThreshold.model_validate(t.model_dump()) == t


# ---------------------------------------------------------------------------
# MinRatioThreshold
# ---------------------------------------------------------------------------


class TestMinRatioThreshold:
    def test_pass_at_or_above_threshold(self):
        t = MinRatioThreshold(pass_at_or_above=0.95)
        assert _check(t, value=1.0).result == "pass"
        assert _check(t, value=0.95).result == "pass"

    def test_fail_below_threshold_no_band(self):
        """Sharp cutoff: no fail_below means any value < pass_at_or_above fails."""
        t = MinRatioThreshold(pass_at_or_above=0.95)
        r = _check(t, value=0.80)
        assert r.result == "fail"

    def test_fail_when_below_fail_below(self):
        t = MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85)
        r = _check(t, value=0.80)
        assert r.result == "fail"

    def test_band_gap_produces_skip(self):
        """Value between fail_below and pass_at_or_above → band_gap skip."""
        t = MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85)
        r = _check(t, value=0.90)
        assert r.result == "skip"
        assert r.details["skip_reason"] == "band_gap"

    def test_round_trip(self):
        t = MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85)
        assert MinRatioThreshold.model_validate(t.model_dump()) == t


# ---------------------------------------------------------------------------
# MaxCountThreshold
# ---------------------------------------------------------------------------


class TestMaxCountThreshold:
    def test_pass_at_or_below(self):
        t = MaxCountThreshold(pass_at_or_below=0)
        assert _check(t, value=0).result == "pass"

    def test_fail_above_sharp(self):
        """Sharp cutoff: no fail_above means any value > pass_at_or_below fails."""
        t = MaxCountThreshold(pass_at_or_below=0)
        assert _check(t, value=1).result == "fail"

    def test_fail_when_above_fail_above(self):
        t = MaxCountThreshold(pass_at_or_below=0, fail_above=3)
        assert _check(t, value=5).result == "fail"

    def test_band_gap_produces_skip(self):
        t = MaxCountThreshold(pass_at_or_below=0, fail_above=3)
        r = _check(t, value=2)
        assert r.result == "skip"
        assert r.details["skip_reason"] == "band_gap"

    def test_round_trip(self):
        t = MaxCountThreshold(pass_at_or_below=0, fail_above=3)
        assert MaxCountThreshold.model_validate(t.model_dump()) == t


# ---------------------------------------------------------------------------
# ScoreBandThreshold — deferred-v1.1 pattern
# ---------------------------------------------------------------------------


class TestScoreBandThreshold:
    def test_both_null_produces_skip_band_gap(self):
        """Deferred-v1.1 pattern: both thresholds null → band_gap skip."""
        t = ScoreBandThreshold(pass_at_or_above=None, fail_below=None)
        r = _check(t, value=0.85)
        assert r.result == "skip"
        assert r.details["skip_reason"] == "band_gap"

    def test_pass_when_above_pass_threshold(self):
        t = ScoreBandThreshold(pass_at_or_above=0.80, fail_below=0.50)
        assert _check(t, value=0.90).result == "pass"

    def test_fail_when_below_fail_threshold(self):
        t = ScoreBandThreshold(pass_at_or_above=0.80, fail_below=0.50)
        assert _check(t, value=0.40).result == "fail"

    def test_band_gap_between_thresholds(self):
        t = ScoreBandThreshold(pass_at_or_above=0.80, fail_below=0.50)
        r = _check(t, value=0.65)
        assert r.result == "skip"
        assert r.details["skip_reason"] == "band_gap"


# ---------------------------------------------------------------------------
# value=None → skip (all threshold kinds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "threshold",
    [
        pytest.param(BooleanThreshold(expected=True), id="boolean"),
        pytest.param(MinRatioThreshold(pass_at_or_above=0.95), id="min_ratio"),
        pytest.param(MaxCountThreshold(pass_at_or_below=0), id="max_count"),
        pytest.param(ScoreBandThreshold(pass_at_or_above=0.80, fail_below=0.50), id="score_band"),
    ],
)
def test_none_value_always_skips(threshold):
    r = _check(threshold, value=None)
    assert r.result == "skip"


# ---------------------------------------------------------------------------
# Explicit skip_reason preserved (deferred_v1.1 pattern)
# ---------------------------------------------------------------------------


def test_explicit_deferred_skip_reason_preserved():
    """CheckResult built with result='skip' and skip_reason stays skip."""
    r = CheckResult(
        id="semantic_accuracy",
        category="graph",
        result="skip",
        value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="Deferred to ADR-020 (v1.1).",
        duration_ms=0,
        details={"skip_reason": "deferred_v1.1", "owner_adr": "ADR-020"},
    )
    assert r.result == "skip"
    assert r.details["skip_reason"] == "deferred_v1.1"
    assert r.details["owner_adr"] == "ADR-020"


# ---------------------------------------------------------------------------
# JSON round-trip for CheckResult
# ---------------------------------------------------------------------------


def test_check_result_json_round_trip():
    original = CheckResult(
        id="schema_validity",
        category="graph",
        result="skip",
        value=True,
        threshold=BooleanThreshold(expected=True),
        rationale="FR-7a",
        duration_ms=42,
    )
    dumped = original.model_dump()
    restored = CheckResult.model_validate(dumped)
    assert restored.id == original.id
    assert restored.result == "pass"  # derived from value=True, expected=True
    assert restored.duration_ms == 42


# ---------------------------------------------------------------------------
# Scorecard envelope
# ---------------------------------------------------------------------------


def test_scorecard_construction():
    from codeograph.evals.scorecard_schema import ReproducibilityInfo

    check = CheckResult(
        id="schema_validity",
        category="graph",
        result="skip",
        value=True,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=1,
    )
    sc = Scorecard(
        schema_version="1.0.0",
        kind="graph",
        corpus_id="spring-rest-sample",
        run_timestamp="2026-05-30T00:00:00Z",
        run_id="run-001",
        reproducibility=ReproducibilityInfo(codeograph_version="0.4.0", seed=0),
        checks=[check],
    )
    assert sc.kind == "graph"
    assert len(sc.checks) == 1
    assert sc.checks[0].result == "pass"
