"""Unit tests for structured logging CLI flags, log filtering, and dual emission.

Scaffolding is AI-generated; the assertion bodies are learner-write per the
DC5 M12 spec. Each test has a ``# TODO(learner):`` marker.
"""

from __future__ import annotations

import logging
from pathlib import Path

from click.testing import CliRunner

from codeograph.cli import main as mod
from codeograph.logging_config import configure_logging
from codeograph.logging_filters import AreaFromContext

# ---------------------------------------------------------------------------
# TestCliLogLevelFlags
# ---------------------------------------------------------------------------


class TestCliLogLevelFlags:
    """Tests for CLI log level configuration, verbosity flags, and mutex rules."""

    def test_log_level_default_is_info(self, monkeypatch) -> None:
        runner = CliRunner()
        seen: list[tuple[str, object]] = []

        def fake_configure_logging(*, console_level: str, out_dir) -> None:
            seen.append((console_level, out_dir))

        monkeypatch.setattr(mod, "configure_logging", fake_configure_logging)

        result = runner.invoke(mod.cli, ["cache", "stats"])

        assert result.exit_code == 0
        assert seen == [("INFO", None)]

    def test_verbose_flag_sets_debug(self, monkeypatch) -> None:
        runner = CliRunner()
        seen: list[tuple[str, object]] = []

        def fake_configure_logging(*, console_level: str, out_dir) -> None:
            seen.append((console_level, out_dir))

        monkeypatch.setattr(mod, "configure_logging", fake_configure_logging)

        result = runner.invoke(mod.cli, ["-v", "cache", "stats"])

        assert result.exit_code == 0
        assert seen == [("DEBUG", None)]

    def test_quiet_flag_sets_warning(self, monkeypatch) -> None:
        runner = CliRunner()
        seen: list[tuple[str, object]] = []

        def fake_configure_logging(*, console_level: str, out_dir) -> None:
            seen.append((console_level, out_dir))

        monkeypatch.setattr(mod, "configure_logging", fake_configure_logging)

        result = runner.invoke(mod.cli, ["-q", "cache", "stats"])

        assert result.exit_code == 0
        assert seen == [("WARNING", None)]

    def test_double_quiet_flag_sets_error(self, monkeypatch) -> None:
        runner = CliRunner()
        seen: list[tuple[str, object]] = []

        def fake_configure_logging(*, console_level: str, out_dir) -> None:
            seen.append((console_level, out_dir))

        monkeypatch.setattr(mod, "configure_logging", fake_configure_logging)

        result = runner.invoke(mod.cli, ["-qq", "cache", "stats"])

        assert result.exit_code == 0
        assert seen == [("ERROR", None)]

    def test_verbose_and_quiet_mutex_raises_usage_error(self, monkeypatch) -> None:
        runner = CliRunner()

        def fake_configure_logging(*, console_level: str, out_dir) -> None:
            raise AssertionError("configure_logging should not be called on invalid flags")

        monkeypatch.setattr(mod, "configure_logging", fake_configure_logging)

        result = runner.invoke(mod.cli, ["-v", "-q", "cache", "stats"])

        assert result.exit_code != 0
        assert isinstance(result.exception, SystemExit) or result.exception is not None
        assert "Cannot specify both -v and -q" in result.output


# ---------------------------------------------------------------------------
# TestDualEmission
# ---------------------------------------------------------------------------


class TestDualEmission:
    """Tests for dual emission (stdout/stderr plaintext vs logs.jsonl file)."""

    def test_dual_emission_writes_plaintext_and_jsonl(self, tmp_path: Path, capsys) -> None:
        configure_logging(console_level="INFO", out_dir=tmp_path)

        log = logging.getLogger("codeograph.test")
        log.debug("debug message")
        log.info("info message")

        captured = capsys.readouterr()
        stderr_text = captured.err
        jsonl_text = (tmp_path / "logs.jsonl").read_text(encoding="utf-8")

        assert "info message" in stderr_text
        assert "debug message" not in stderr_text
        assert "info message" in jsonl_text
        assert "debug message" in jsonl_text


# ---------------------------------------------------------------------------
# TestAreaFromContextFilter
# ---------------------------------------------------------------------------


class TestAreaFromContextFilter:
    """Tests for the AreaFromContext filter parsing log contexts correctly."""

    def test_area_extracted_from_context_extra(self) -> None:
        record = logging.LogRecord(
            name="codeograph.anything",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.context = {"area": "parser"}

        filt = AreaFromContext()
        assert filt.filter(record) is True
        assert getattr(record, "area") == "parser"

    def test_area_falls_back_to_logger_name(self) -> None:
        record = logging.LogRecord(
            name="codeograph.passes.pass1",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        filt = AreaFromContext()
        assert filt.filter(record) is True
        assert getattr(record, "area") == "pass1"
