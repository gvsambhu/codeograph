"""
FileParserDispatcher — try AST parse, fall back to regex on failure.

This is the single entry point the pipeline uses per .java file. Callers
never import JavaFileParser or RegexFallback directly; they receive a
ParsedFile regardless of which strategy succeeded.

Fallback trigger: JavaParseError from JavaFileParser (JAR exits non-zero,
stdout is not valid JSON, or java not found). The fallback is logged at
WARNING so operators can monitor degradation rates. All other exceptions
propagate — they indicate infrastructure problems, not parse failures.

Typical wiring (done once at pipeline startup, not per file):

    from codeograph.parser import (
        FileParserDispatcher, JavaFileParser, RegexFallback
    )

    dispatcher = FileParserDispatcher(
        java_parser=JavaFileParser(),   # resolves jar + java automatically
        fallback=RegexFallback(),
    )

    for java_file in corpus_files:
        parsed = dispatcher.parse(java_file, corpus_root)
        # parsed["extraction_mode"] tells you which path was taken
"""

from __future__ import annotations

import logging
from pathlib import Path

from codeograph.parser.java_file_parser import JavaFileParser, JavaParseError
from codeograph.parser.models import ParsedFile
from codeograph.parser.regex_fallback import RegexFallback

logger = logging.getLogger(__name__)


class FileParserDispatcher:
    """
    Orchestrates AST parsing with automatic regex fallback.

    Stateless after construction — safe to call parse() from multiple
    threads if the underlying parser/fallback are also thread-safe.
    (JavaFileParser spawns a subprocess per call; RegexFallback is
    pure-function; both are safe.)

    :param java_parser:  JavaFileParser instance (owns the JAR subprocess).
    :param fallback:     RegexFallback instance (pure regex extraction).
    """

    def __init__(
        self,
        java_parser: JavaFileParser,
        fallback: RegexFallback,
    ) -> None:
        self._java_parser = java_parser
        self._fallback = fallback

    def parse(self, java_file: Path, corpus_root: Path) -> ParsedFile:
        """
        Parse one .java file, falling back to regex if the JAR fails.

        :param java_file:    Absolute path to the .java source file.
        :param corpus_root:  Absolute path to the corpus root directory.
        :returns:            ParsedFile with extraction_mode="ast" on success
                             or extraction_mode="regex" on fallback.
        """
        try:
            return self._java_parser.parse(java_file, corpus_root)
        except JavaParseError as exc:
            logger.warning(
                "AST parse failed for %s (%s), falling back to regex",
                java_file,
                exc,
            )
            return self._fallback.parse(java_file, corpus_root)
