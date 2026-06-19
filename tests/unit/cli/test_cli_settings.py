"""Unit tests for settings validation error handling in the CLI."""

from __future__ import annotations

from click.testing import CliRunner

from codeograph.cli.main import cli


def test_settings_validation_error_cli(monkeypatch, tmp_path):
    """An invalid configuration setting (e.g. CODEOGRAPH_LLM_CONCURRENCY=999)

    should yield a non-zero exit and a readable error message without a traceback.
    """
    monkeypatch.setenv("CODEOGRAPH_LLM_CONCURRENCY", "999")
    runner = CliRunner()
    # Use tmp_path to ensure the output directory does not exist or is empty
    out_dir = tmp_path / "dummy_out"
    result = runner.invoke(cli, ["run", "dummy_input", "--out", str(out_dir)])

    assert result.exit_code != 0
    # Confirm it does not raise a traceback
    assert "Traceback" not in result.output
    # Confirm the offending environment variable and remedy are present in the output
    assert "CODEOGRAPH_LLM_CONCURRENCY" in result.output
    assert "concurrency must be between 1 and 50" in result.output.lower()
