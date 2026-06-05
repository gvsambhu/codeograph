"""Unit tests for eval CLI subcommands and llm_judge check (M7/M8 coverage)."""

from __future__ import annotations

import json
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


def test_eval_report_routed_through_top_level_cli(tmp_path: Path):
    """eval report must be reachable via the top-level eval group (Issue #1).

    Previously `codeograph eval report <dir>` parsed 'report' as the
    OUTPUT_DIR positional arg on the group, making the subcommand unreachable.
    This test goes through eval_cli (not report_cmd directly) to catch
    any future routing regression.
    """
    from codeograph.cli.eval import eval_cli

    _write_scorecard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(eval_cli, ["report", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Evaluation Report" in result.output


def test_report_output_md_writes_file(tmp_path: Path):
    """--output-md <file> writes a real markdown file (Issue #4)."""
    from codeograph.cli.eval_report import report_cmd

    _write_scorecard(tmp_path)
    md_path = tmp_path / "report.md"
    runner = CliRunner()
    result = runner.invoke(report_cmd, [str(tmp_path), "--output-md", str(md_path)])
    assert result.exit_code == 0, result.output
    assert md_path.exists(), "--output-md did not create the file"
    content = md_path.read_text(encoding="utf-8")
    assert "Evaluation Report" in content
    assert "placeholder" not in content.lower()


def test_report_output_json_writes_valid_json(tmp_path: Path):
    """--output-json <file> writes valid JSON deserializable to ReportResult (Issue #4)."""
    from codeograph.cli.eval_report import report_cmd
    from codeograph.evals.report import ReportResult

    _write_scorecard(tmp_path)
    json_path = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(report_cmd, [str(tmp_path), "--output-json", str(json_path)])
    assert result.exit_code == 0, result.output
    assert json_path.exists(), "--output-json did not create the file"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    report = ReportResult.model_validate(data)
    assert report.overall in ("pass", "fail", "mixed")


def test_eval_run_routed_through_top_level_cli(tmp_path: Path):
    """eval run must be reachable and produce JSON scorecard output (Issue #1)."""
    from unittest.mock import MagicMock, patch

    from codeograph.cli.eval import eval_cli

    # Write a minimal manifest so the run_cmd manifest check passes
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    mock_sc = MagicMock()
    mock_sc.model_dump_json.return_value = '{"kind":"graph"}'
    mock_sc.checks = []

    with patch("codeograph.cli.eval.EvalRunner") as MockRunner:
        MockRunner.return_value.run.return_value = [mock_sc]
        runner = CliRunner()
        result = runner.invoke(eval_cli, ["run", str(tmp_path)])

    assert result.exit_code == 0, result.output
