"""Unit tests for eval CLI subcommands and llm_judge check (M7/M8 coverage)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from codeograph.evals.checks.code.llm_judge import check_llm_judge

# ---------------------------------------------------------------------------
# check_llm_judge — always deferred skip
# ---------------------------------------------------------------------------


def test_llm_judge_always_skips(tmp_path: Path):
    result = check_llm_judge(tmp_path, "ts")
    assert result.result == "skip"
    assert result.id == "llm_judge"
    assert result.details.get("skip_reason") == "deferred_v1.1"
    assert result.details.get("owner_adr") == "ADR-020"


# ---------------------------------------------------------------------------
# eval report CLI — basic happy path
# ---------------------------------------------------------------------------


def _write_scorecard(out_dir: Path, corpus_id: str = "test") -> None:
    """Write a minimal graph-scorecard.json so the report CLI can read it."""
    from codeograph.evals.scorecard_schema import (
        BooleanThreshold,
        CheckResult,
        ReproducibilityInfo,
        Scorecard,
    )
    sc = Scorecard(
        schema_version="1.0.0",
        kind="graph",
        corpus_id=corpus_id,
        run_timestamp="2026-05-30T00:00:00Z",
        run_id="run-001",
        reproducibility=ReproducibilityInfo(codeograph_version="0.1.0", seed=0),
        checks=[
            CheckResult(
                id="schema_validity",
                category="graph",
                value=True,
                threshold=BooleanThreshold(expected=True),
                rationale="test",
                duration_ms=1,
            )
        ],
    )
    evals_dir = out_dir / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "graph-scorecard.json").write_text(sc.model_dump_json(), encoding="utf-8")


def test_report_cmd_exits_0_on_pass(tmp_path: Path):
    from codeograph.cli.eval_report import report_cmd
    _write_scorecard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(report_cmd, [str(tmp_path)])
    assert result.exit_code == 0
    assert "Evaluation Report" in result.output


def test_report_cmd_requires_at_least_one_dir():
    from codeograph.cli.eval_report import report_cmd
    runner = CliRunner()
    result = runner.invoke(report_cmd, [])
    assert result.exit_code != 0
