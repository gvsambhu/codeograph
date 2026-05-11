"""
Unit tests for JavaFileParser (codeograph/parser/java_file_parser.py).

All subprocess.run calls are mocked so no JVM is required.
Tests that invoke the real parser.jar are marked @pytest.mark.integration
and will be collected but skipped unless the integration suite is run.

Coverage plan:
  - parse(): success path (exit 0, valid JSON) → ParsedFile returned
  - parse(): non-zero exit → JavaParseError raised, message contains exit code
  - parse(): exit 0 but invalid JSON → JavaParseError raised
  - parse(): exit 0, empty stdout → JavaParseError raised (json.loads("") fails)
  - Command construction: java + -jar + jar_path + java_file + corpus_root
  - _resolve_java(): JAVA_HOME set → uses $JAVA_HOME/bin/java
  - _resolve_java(): no JAVA_HOME, java on PATH → shutil.which("java")
  - _resolve_java(): neither JAVA_HOME nor PATH → EnvironmentError
  - Custom jar_path and java_bin constructor args respected
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeograph.parser.java_file_parser import JavaFileParser, JavaParseError

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


@pytest.fixture
def fake_jar(tmp_path: Path) -> Path:
    j = tmp_path / "parser.jar"
    j.write_bytes(b"")  # contents irrelevant — subprocess is mocked
    return j


def _make_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a mock CompletedProcess-like object."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ---------------------------------------------------------------------------
# TestParseSuccess
# ---------------------------------------------------------------------------

class TestParseSuccess:

    def test_returns_parsed_file_on_success(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "com.example.Foo", "kind": "class", "name": "Foo"}
        mock_result = _make_completed(returncode=0, stdout=json.dumps(payload))

        with patch("subprocess.run", return_value=mock_result):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            pf = parser.parse(java_file, corpus_root)

        assert pf["id"] == "com.example.Foo"
        assert pf["kind"] == "class"

    def test_extra_fields_in_json_passed_through(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {
            "id": "a.b.C",
            "kind": "class",
            "name": "C",
            "extraction_mode": "ast",
            "annotations": [],
        }
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            pf = parser.parse(java_file, corpus_root)

        assert pf["extraction_mode"] == "ast"
        assert pf["annotations"] == []


# ---------------------------------------------------------------------------
# TestParseFailures
# ---------------------------------------------------------------------------

class TestParseFailures:

    def test_nonzero_exit_raises_java_parse_error(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        mock_result = _make_completed(returncode=1, stderr="Syntax error")
        with patch("subprocess.run", return_value=mock_result):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            with pytest.raises(JavaParseError, match="exit 1"):
                parser.parse(java_file, corpus_root)

    def test_nonzero_exit_message_includes_stderr(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        mock_result = _make_completed(returncode=2, stderr="OutOfMemoryError")
        with patch("subprocess.run", return_value=mock_result):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            with pytest.raises(JavaParseError, match="OutOfMemoryError"):
                parser.parse(java_file, corpus_root)

    def test_invalid_json_raises_java_parse_error(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        mock_result = _make_completed(returncode=0, stdout="not-valid-json{{")
        with patch("subprocess.run", return_value=mock_result):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            with pytest.raises(JavaParseError, match="invalid JSON"):
                parser.parse(java_file, corpus_root)

    def test_empty_stdout_raises_java_parse_error(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        mock_result = _make_completed(returncode=0, stdout="")
        with patch("subprocess.run", return_value=mock_result):
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            with pytest.raises(JavaParseError):
                parser.parse(java_file, corpus_root)


# ---------------------------------------------------------------------------
# TestCommandConstruction
# ---------------------------------------------------------------------------

class TestCommandConstruction:

    def test_command_contains_java_bin(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "x.Y", "kind": "class", "name": "Y"}
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))) as mock_run:
            parser = JavaFileParser(jar_path=fake_jar, java_bin="/usr/bin/java")
            parser.parse(java_file, corpus_root)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/java"

    def test_command_contains_jar_flag(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "x.Y", "kind": "class", "name": "Y"}
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))) as mock_run:
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            parser.parse(java_file, corpus_root)

        cmd = mock_run.call_args[0][0]
        assert "-jar" in cmd

    def test_command_contains_jar_path(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "x.Y", "kind": "class", "name": "Y"}
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))) as mock_run:
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            parser.parse(java_file, corpus_root)

        cmd = mock_run.call_args[0][0]
        assert str(fake_jar) in cmd

    def test_command_contains_java_file_and_corpus_root(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "x.Y", "kind": "class", "name": "Y"}
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))) as mock_run:
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            parser.parse(java_file, corpus_root)

        cmd = mock_run.call_args[0][0]
        assert str(java_file) in cmd
        assert str(corpus_root) in cmd

    def test_subprocess_run_called_with_capture_output(
        self, java_file: Path, corpus_root: Path, fake_jar: Path
    ) -> None:
        payload = {"id": "x.Y", "kind": "class", "name": "Y"}
        with patch("subprocess.run", return_value=_make_completed(stdout=json.dumps(payload))) as mock_run:
            parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
            parser.parse(java_file, corpus_root)

        kwargs = mock_run.call_args[1]
        assert kwargs.get("capture_output") is True
        assert kwargs.get("text") is True
        assert kwargs.get("check") is False


# ---------------------------------------------------------------------------
# TestResolveJava
# ---------------------------------------------------------------------------

class TestResolveJava:

    def test_java_home_takes_priority(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        java_home = tmp_path / "jdk"
        (java_home / "bin").mkdir(parents=True)
        (java_home / "bin" / "java").write_text("stub")

        monkeypatch.setenv("JAVA_HOME", str(java_home))

        def _which(name: str, path: str | None = None) -> str | None:
            if path and "jdk" in path:
                return str(java_home / "bin" / "java")
            return None

        with patch("shutil.which", side_effect=_which):
            result = JavaFileParser._resolve_java()

        assert "jdk" in result

    def test_falls_back_to_path_when_no_java_home(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("shutil.which", return_value="/usr/bin/java") as mock_which:
            result = JavaFileParser._resolve_java()

        assert result == "/usr/bin/java"
        mock_which.assert_called_with("java")

    def test_raises_environment_error_when_java_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JAVA_HOME", raising=False)

        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="java not found"):
                JavaFileParser._resolve_java()


# ---------------------------------------------------------------------------
# TestConstructorArgs
# ---------------------------------------------------------------------------

class TestConstructorArgs:

    def test_custom_java_bin_stored(self, fake_jar: Path) -> None:
        parser = JavaFileParser(jar_path=fake_jar, java_bin="/opt/java/bin/java")
        assert parser._java == "/opt/java/bin/java"

    def test_custom_jar_path_stored(self, fake_jar: Path) -> None:
        parser = JavaFileParser(jar_path=fake_jar, java_bin="java")
        assert parser._jar == fake_jar


# ---------------------------------------------------------------------------
# Integration-only tests (require real JVM and parser.jar)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestParseRealJar:
    """
    These tests invoke the real parser.jar via a live JVM subprocess.
    They are excluded from the unit suite and run as part of the
    golden-graph integration suite (ADR-007).

    Run with:  pytest -m integration
    Skip with: pytest -m "not integration"  (default CI configuration)
    """

    def test_parse_real_java_file(self, tmp_path: Path) -> None:
        """
        Write a minimal valid .java file and parse it with the real JAR.
        Asserts the output carries id, kind, and extraction_mode="ast".
        """
        src = (
            "package com.example;\n"
            "public class Hello {\n"
            "    public String greet() { return \"hello\"; }\n"
            "}\n"
        )
        java_file = tmp_path / "Hello.java"
        java_file.write_text(src, encoding="utf-8")

        parser = JavaFileParser()  # uses default jar path and resolves java
        pf = parser.parse(java_file, tmp_path)

        assert pf["id"] == "com.example.Hello"
        assert pf["kind"] == "class"
        assert pf["extraction_mode"] == "ast"
