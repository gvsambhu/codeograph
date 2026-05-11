"""
JavaFileParser — invokes the fat JAR as a subprocess and parses its stdout.

The JAR (parser/lib/parser.jar) accepts:
    java -jar parser.jar <absolute-java-file> <corpus-root>

It writes one JSON envelope to stdout on success (exit 0) or an error
message to stderr on failure (exit non-zero). This module handles the
subprocess lifecycle, JSON decoding, and error surfacing.

Falls back to RegexFallback via FileParserDispatcher — never called directly
for the fallback path.

See ADR-003 for the subprocess contract.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from codeograph.parser.models import ParsedFile

logger = logging.getLogger(__name__)

# Default JAR location: parser/lib/parser.jar relative to this file's package.
_DEFAULT_JAR = Path(__file__).parent / "lib" / "parser.jar"


class JavaParseError(Exception):
    """
    Raised when the JAR subprocess exits non-zero or its stdout is not
    valid JSON. Contains the underlying reason as the exception message.

    FileParserDispatcher catches this specifically so it can fall back to
    RegexFallback without accidentally swallowing unrelated errors.
    """


class JavaFileParser:
    """
    Thin wrapper around the JavaParserRunner fat JAR.

    Constructs the subprocess command, runs it, reads stdout, and returns
    a ParsedFile TypedDict. On any failure, raises JavaParseError.

    :param jar_path:  Path to parser.jar. Defaults to parser/lib/parser.jar
                      inside the installed package.
    :param java_bin:  Path or name of the java executable.
                      None → resolved automatically via JAVA_HOME then PATH.
    """

    def __init__(
        self,
        jar_path: Path = _DEFAULT_JAR,
        java_bin: str | None = None,
    ) -> None:
        self._jar = jar_path
        self._java = java_bin if java_bin is not None else self._resolve_java()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, java_file: Path, corpus_root: Path) -> ParsedFile:
        """
        Parse one .java file via the JAR and return the intermediate envelope.

        :param java_file:   Absolute path to the .java source file.
        :param corpus_root: Absolute path to the corpus root directory.
                            Used by the JAR to compute the corpus-relative
                            source_file path in the envelope.
        :raises JavaParseError: If the JAR exits non-zero, stdout is empty,
                                 or stdout is not valid JSON.
        """
        command: list[str] = [
            self._java,
            "-jar",
            str(self._jar),
            str(java_file),
            str(corpus_root),
        ]

        logger.debug("AST parse: %s", java_file)
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise JavaParseError(
                f"Java parser failed (exit {result.returncode}): {stderr}"
            )

        stdout = result.stdout or ""
        try:
            result_dict = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise JavaParseError(
                f"Java parser produced invalid JSON: {e}. Raw stdout:\n{stdout}"
            ) from e

        return cast(ParsedFile, result_dict)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_java() -> str:
        """
        Locate the java executable using JAVA_HOME then PATH.

        Resolution order:
          1. $JAVA_HOME/bin/java  (explicit environment override — CI/CD friendly)
          2. shutil.which("java") (java is on PATH — developer machine default)

        :raises EnvironmentError: If java cannot be found by either method.
        """
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            # Use shutil.which against the bin dir — it appends .exe on Windows
            # automatically, so Path / "java" would fail there without this.
            found_in_home = shutil.which("java", path=str(Path(java_home) / "bin"))
            if found_in_home:
                return found_in_home

        found = shutil.which("java")
        if found:
            return found

        raise OSError(
            "java not found — set JAVA_HOME or add java to PATH"
        )
