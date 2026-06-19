"""Unit tests for codeograph/evals/report.py (ADR-017 Fork 7)."""

from __future__ import annotations

from pathlib import Path

from codeograph.evals.report import generate_report, render_markdown, ReportResult
from codeograph.evals.models import (
    BooleanThreshold,
    CheckResult,
    MinRatioThreshold,
    ReproducibilityInfo,
    ScoreBandThreshold,
    Scorecard,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scorecard(
    kind: str,
    corpus_id: str,
    checks: list[CheckResult],
) -> Scorecard:
    return Scorecard(
        schema_version="1.0.0",
        kind=kind,  # type: ignore[arg-type]
        corpus_id=corpus_id,
        run_timestamp="2026-05-30T00:00:00Z",
        run_id="run-001",
        reproducibility=ReproducibilityInfo(codeograph_version="0.1.0", seed=0),
        checks=checks,
    )


def _pass_check(check_id: str, value: bool | float = True) -> CheckResult:
    return CheckResult(
        id=check_id,
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=1,
    )


def _skip_check(check_id: str) -> CheckResult:
    return CheckResult(
        id=check_id,
        category="graph",
        result="skip",
        value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="test",
        duration_ms=0,
        details={"skip_reason": "deferred_v1.1"},
    )


def _write_scorecard_file(out_dir: Path, sc: Scorecard) -> None:
    evals_dir = out_dir / "evals"
    evals_dir.mkdir(exist_ok=True)
    if sc.kind == "graph":
        filename = "graph-scorecard.json"
    else:
        filename = f"{sc.kind}-scorecard.json"
    (evals_dir / filename).write_text(sc.model_dump_json(), encoding="utf-8")


# ---------------------------------------------------------------------------
# EvalReport.generate
# ---------------------------------------------------------------------------


def test_generate_empty_dirs_returns_pass(tmp_path: Path):
    """No scorecards found → all_results empty → overall pass."""
    result = generate_report([tmp_path])
    assert result.overall == "pass"
    assert result.kinds == {}


def test_generate_single_corpus_all_pass(tmp_path: Path):
    sc = _make_scorecard("graph", "spring-rest-sample", [_pass_check("schema_validity")])
    _write_scorecard_file(tmp_path, sc)
    result = generate_report([tmp_path])
    assert result.overall == "pass"
    assert "graph" in result.kinds


def test_generate_aggregates_across_two_corpora(tmp_path: Path):
    dir_a = tmp_path / "corpus_a"
    dir_a.mkdir()
    dir_b = tmp_path / "corpus_b"
    dir_b.mkdir()

    sc_a = _make_scorecard("graph", "corpus-a", [_pass_check("schema_validity")])
    sc_b = _make_scorecard("graph", "corpus-b", [_pass_check("schema_validity")])
    _write_scorecard_file(dir_a, sc_a)
    _write_scorecard_file(dir_b, sc_b)

    result = generate_report([dir_a, dir_b])
    assert result.overall == "pass"
    graph_checks = result.kinds["graph"]
    schema_check = next(c for c in graph_checks if c.id == "schema_validity")
    assert "corpus-a" in schema_check.corpus_results
    assert "corpus-b" in schema_check.corpus_results


def test_generate_overall_fail_when_any_fails(tmp_path: Path):
    fail_check = CheckResult(
        id="schema_validity",
        category="graph",
        value=False,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=1,
    )
    sc = _make_scorecard("graph", "corpus-a", [fail_check])
    _write_scorecard_file(tmp_path, sc)
    result = generate_report([tmp_path])
    assert result.overall == "fail"


def test_generate_aggregates_min_ratio_mean(tmp_path: Path):
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    check_a = CheckResult(
        id="structural_completeness",
        category="graph",
        value=1.0,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="test",
        duration_ms=1,
    )
    check_b = CheckResult(
        id="structural_completeness",
        category="graph",
        value=0.8,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="test",
        duration_ms=1,
    )
    _write_scorecard_file(dir_a, _make_scorecard("graph", "a", [check_a]))
    _write_scorecard_file(dir_b, _make_scorecard("graph", "b", [check_b]))

    result = generate_report([dir_a, dir_b])
    agg = next(c for c in result.kinds["graph"] if c.id == "structural_completeness")
    assert agg.aggregate_value.get("mean") is not None


# ---------------------------------------------------------------------------
# EvalReport.render_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_contains_table_and_header(tmp_path: Path):
    sc = _make_scorecard("graph", "spring-rest-sample", [_pass_check("schema_validity")])
    _write_scorecard_file(tmp_path, sc)
    result = generate_report([tmp_path])
    md = render_markdown(result)
    assert "# Evaluation Report" in md
    assert "schema_validity" in md
    assert "spring-rest-sample" in md


def test_render_markdown_overall_emoji():
    result = ReportResult(overall="pass", kinds={})
    md = render_markdown(result)
    assert "✅" in md or "PASS" in md.upper()
