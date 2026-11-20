"""Integration test for codeograph run --eval (reproducibility check with in-memory source path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codeograph.cli.main import cli

pytestmark = [pytest.mark.slow, pytest.mark.external]

_FIXTURE_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "codeograph-corpus"


def test_run_eval_reproducibility_passes(tmp_path: Path) -> None:
    """Invoking run with --eval executes evaluation and reproducibility check passes."""
    runner = CliRunner()
    out_dir = tmp_path / "out"

    result = runner.invoke(
        cli,
        [
            "run",
            str(_FIXTURE_CORPUS),
            "--out",
            str(out_dir),
            "--ast-only",
            "--eval",
        ],
    )

    # Failing scorecard exits 1 by design; no raw exception may escape.
    assert result.exception is None or (isinstance(result.exception, SystemExit) and result.exception.code == 1), (
        f"Unexpected exception: {result.exception}"
    )

    manifest_path = out_dir / "manifest.json"
    assert manifest_path.exists(), f"manifest.json was not created: {result.output}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "scorecards" in manifest
    assert "graph" in manifest["scorecards"]

    scorecard_relpath = manifest["scorecards"]["graph"]["path"]
    scorecard_path = out_dir / scorecard_relpath
    assert scorecard_path.exists(), f"Scorecard file {scorecard_path} does not exist"

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    repro = next((c for c in scorecard.get("checks", []) if c.get("id") == "reproducibility"), None)
    assert repro is not None, "reproducibility check missing from graph scorecard"
    assert repro["result"] == "pass", f"reproducibility check did not pass: {repro}"
