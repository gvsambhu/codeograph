"""
Unit tests for FileParserDispatcher (codeograph/parser/file_parser_dispatcher.py).

Both JavaFileParser and RegexFallback are mocked — no JVM, no real files.
The dispatcher's only job is: try AST, catch JavaParseError → regex, let
other exceptions propagate.

Coverage plan:
  - AST success path → ParsedFile from java_parser.parse() returned unchanged
  - JavaParseError → fallback invoked, ParsedFile from fallback returned
  - Non-JavaParseError exception from java_parser → propagates (not caught)
  - extraction_mode reflects which path was taken
  - JavaParseError from java_parser is logged at WARNING (smoke test via caplog)
  - fallback NOT called when AST succeeds
  - java_parser NOT retried after JavaParseError (fallback called exactly once)
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
from codeograph.parser.java_file_parser import JavaParseError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ast_pf(fqcn: str = "com.example.Foo") -> dict:
    return {"id": fqcn, "kind": "class", "name": "Foo", "extraction_mode": "ast"}


def _regex_pf(fqcn: str = "com.example.Foo") -> dict:
    return {"id": fqcn, "kind": "class", "name": "Foo", "extraction_mode": "regex"}


def _make_dispatcher(
    ast_result: dict | Exception | None = None,
    regex_result: dict | None = None,
) -> tuple[FileParserDispatcher, MagicMock, MagicMock]:
    """
    Build a FileParserDispatcher with mocked java_parser and fallback.

    :param ast_result:   Return value for java_parser.parse(), or an Exception
                         class/instance to raise instead.
    :param regex_result: Return value for fallback.parse().
    :returns:            (dispatcher, mock_java_parser, mock_fallback)
    """
    mock_java = MagicMock()
    mock_fallback = MagicMock()

    if isinstance(ast_result, dict):
        mock_java.parse.return_value = ast_result
    elif ast_result is not None:
        mock_java.parse.side_effect = ast_result

    if regex_result is not None:
        mock_fallback.parse.return_value = regex_result

    dispatcher = FileParserDispatcher(java_parser=mock_java, fallback=mock_fallback)
    return dispatcher, mock_java, mock_fallback


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def java_file(tmp_path: Path) -> Path:
    f = tmp_path / "Foo.java"
    f.write_text("public class Foo {}", encoding="utf-8")
    return f


@pytest.fixture
def corpus_root(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# TestAstSuccessPath
# ---------------------------------------------------------------------------

class TestAstSuccessPath:

    def test_returns_ast_parsed_file(self, java_file: Path, corpus_root: Path) -> None:
        pf = _ast_pf()
        dispatcher, _, _ = _make_dispatcher(ast_result=pf)
        result = dispatcher.parse(java_file, corpus_root)
        assert result is pf

    def test_extraction_mode_ast(self, java_file: Path, corpus_root: Path) -> None:
        pf = _ast_pf()
        dispatcher, _, _ = _make_dispatcher(ast_result=pf)
        result = dispatcher.parse(java_file, corpus_root)
        assert result["extraction_mode"] == "ast"

    def test_fallback_not_called_on_success(self, java_file: Path, corpus_root: Path) -> None:
        pf = _ast_pf()
        dispatcher, _, mock_fallback = _make_dispatcher(ast_result=pf)
        dispatcher.parse(java_file, corpus_root)
        mock_fallback.parse.assert_not_called()

    def test_java_parser_called_with_correct_args(
        self, java_file: Path, corpus_root: Path
    ) -> None:
        pf = _ast_pf()
        dispatcher, mock_java, _ = _make_dispatcher(ast_result=pf)
        dispatcher.parse(java_file, corpus_root)
        mock_java.parse.assert_called_once_with(java_file, corpus_root)


# ---------------------------------------------------------------------------
# TestFallbackPath
# ---------------------------------------------------------------------------

class TestFallbackPath:

    def test_returns_regex_parsed_file_on_java_parse_error(
        self, java_file: Path, corpus_root: Path
    ) -> None:
        regex_pf = _regex_pf()
        dispatcher, _, _ = _make_dispatcher(
            ast_result=JavaParseError("JAR failed"),
            regex_result=regex_pf,
        )
        result = dispatcher.parse(java_file, corpus_root)
        assert result is regex_pf

    def test_extraction_mode_regex_on_fallback(
        self, java_file: Path, corpus_root: Path
    ) -> None:
        regex_pf = _regex_pf()
        dispatcher, _, _ = _make_dispatcher(
            ast_result=JavaParseError("JAR failed"),
            regex_result=regex_pf,
        )
        result = dispatcher.parse(java_file, corpus_root)
        assert result["extraction_mode"] == "regex"

    def test_fallback_called_exactly_once(self, java_file: Path, corpus_root: Path) -> None:
        regex_pf = _regex_pf()
        dispatcher, _, mock_fallback = _make_dispatcher(
            ast_result=JavaParseError("JAR failed"),
            regex_result=regex_pf,
        )
        dispatcher.parse(java_file, corpus_root)
        mock_fallback.parse.assert_called_once_with(java_file, corpus_root)

    def test_java_parse_error_logged_at_warning(
        self, java_file: Path, corpus_root: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Fallback path must be observable via WARNING log for operators."""
        dispatcher, _, _ = _make_dispatcher(
            ast_result=JavaParseError("exit 1"),
            regex_result=_regex_pf(),
        )
        with caplog.at_level(logging.WARNING, logger="codeograph.parser.file_parser_dispatcher"):
            dispatcher.parse(java_file, corpus_root)

        assert any("regex" in rec.message.lower() or "fallback" in rec.message.lower()
                   for rec in caplog.records)


# ---------------------------------------------------------------------------
# TestExceptionPropagation
# ---------------------------------------------------------------------------

class TestExceptionPropagation:

    def test_non_java_parse_error_propagates(
        self, java_file: Path, corpus_root: Path
    ) -> None:
        """
        If java_parser.parse() raises something other than JavaParseError
        (e.g. PermissionError, AttributeError), the dispatcher must NOT catch it.
        """
        dispatcher, _, _ = _make_dispatcher(
            ast_result=RuntimeError("unexpected crash"),
        )
        with pytest.raises(RuntimeError, match="unexpected crash"):
            dispatcher.parse(java_file, corpus_root)

    def test_non_java_parse_error_fallback_not_called(
        self, java_file: Path, corpus_root: Path
    ) -> None:
        dispatcher, _, mock_fallback = _make_dispatcher(
            ast_result=RuntimeError("crash"),
        )
        with pytest.raises(RuntimeError):
            dispatcher.parse(java_file, corpus_root)
        mock_fallback.parse.assert_not_called()

    def test_value_error_propagates(self, java_file: Path, corpus_root: Path) -> None:
        dispatcher, _, _ = _make_dispatcher(ast_result=ValueError("bad value"))
        with pytest.raises(ValueError):
            dispatcher.parse(java_file, corpus_root)


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------

class TestConstructor:

    def test_constructor_stores_java_parser(self) -> None:
        mock_java = MagicMock()
        mock_fallback = MagicMock()
        dispatcher = FileParserDispatcher(java_parser=mock_java, fallback=mock_fallback)
        assert dispatcher._java_parser is mock_java

    def test_constructor_stores_fallback(self) -> None:
        mock_java = MagicMock()
        mock_fallback = MagicMock()
        dispatcher = FileParserDispatcher(java_parser=mock_java, fallback=mock_fallback)
        assert dispatcher._fallback is mock_fallback
