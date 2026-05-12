"""
RegexFallback — degraded structural extraction via regex when the JAR fails.

This path is taken when JavaFileParser raises JavaParseError (JAR exits
non-zero, unparseable syntax, or java not found). It extracts what can
be recovered reliably from plain text without a full AST.

Extraction coverage vs the AST path:
  ✓ package + class name → id, name
  ✓ class-level annotation names → annotations, stereotype
  ✓ import statements → imports
  ✓ field declarations (type + name only — no injection metadata)
  ✓ method signatures (name + return type only — no body analysis)
  ✗ table_name, qualifier, generation, column, http_metadata
  ✗ is_autowired / is_id (requires field annotation correlation)
  ✗ calls (requires body traversal)
  ✗ line_range (omitted rather than guessed)

The returned ParsedFile always carries extraction_mode="regex" so the
graph builder and any downstream quality metrics can treat it accordingly.

Design note: this class never raises — it returns a best-effort ParsedFile.
A completely unreadable file returns a minimal envelope with source_file
populated and empty arrays for everything else. Errors are logged at WARNING.

Patterns lifted and refactored from:
  codeograph-legacy/part-2-analysis-tool/reader/code_reader.py
  codeograph-legacy/part-2-analysis-tool/reader/dependency_extractor.py
  codeograph-legacy/part-2-analysis-tool/reader/categorizer.py
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from codeograph.parser.models import (
    FieldFact,
    MethodFact,
    ParsedFile,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Package declaration:  package com.example.service;
_RE_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

# Any import (static or wildcard):  import static com.example.Foo.*;
_RE_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE)

# Annotation simple name before any attribute list: @Service, @RequestMapping(...)
# Lifted from legacy code_reader._ANNOTATION_RE — captures just the name group.
_RE_ANNOTATION = re.compile(r"@(\w+)(?:\([^)]*\))?")

# Primary type declaration — captures (kind_keyword, simple_name).
# Handles: class, interface, enum, record, @interface
# Lifted and extended from legacy code_reader._CLASS_DECL_RE.
_RE_TYPE_DECL = re.compile(
    r"(?:^|(?<=\s))"  # start of line or preceded by whitespace
    r"(?:(?:public|protected|private|abstract|final|static|sealed)\s+)*"
    r"(@?interface|class|enum|record)\s+"  # kind keyword (@interface is one token here)
    r"(\w+)",  # simple type name
    re.MULTILINE,
)

# Field declaration inside a class body.
# Matches the most common modifiers then captures type and name.
# Intentionally conservative — misses complex generics, prefers no false positives.
# Refactored from legacy dependency_extractor._FIELD_RE (which only matched private final).
_RE_FIELD = re.compile(
    r"^\s{4,}"  # indented ≥4 spaces
    r"(?:(?:private|public|protected|static|final|volatile|transient)\s+)+"
    r"([\w][\w<>\[\]]*)\s+"  # type (simple, no nested generics)
    r"(\w+)\s*(?:[=;,]|//)",  # name then = ; , or inline comment
    re.MULTILINE,
)

# Method signature: modifiers + return-type + name + opening paren.
# Excludes constructors (they have no return type) by requiring a return-type word.
_RE_METHOD = re.compile(
    r"^\s{4,}"  # indented ≥4 spaces
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|default)\s+)*"
    r"([\w][\w<>\[\]]*)\s+"  # return type
    r"(\w+)\s*\(",  # method name + (
    re.MULTILINE,
)

# Known Spring stereotype annotation names — mirrors JavaParserRunner.STEREOTYPES.
_STEREOTYPES: frozenset[str] = frozenset(
    {
        "Component",
        "Service",
        "Repository",
        "Controller",
        "RestController",
        "Configuration",
        "ControllerAdvice",
        "Entity",
        "SpringBootApplication",
    }
)

# Method names that are almost certainly not real methods (noise from regex).
# `if`, `while`, `for`, `switch`, etc. can appear as "return type + name" false positives.
_METHOD_KEYWORD_NOISE: frozenset[str] = frozenset(
    {
        "if",
        "while",
        "for",
        "switch",
        "catch",
        "return",
        "new",
        "else",
        "try",
        "throw",
        "assert",
        "do",
        "case",
        "default",
    }
)


class RegexFallback:
    """
    Best-effort Java structural extractor using regex pattern matching.

    Instantiate once and call parse() per file. Stateless — safe to reuse
    across files from multiple threads.
    """

    def parse(self, java_file: Path, corpus_root: Path) -> ParsedFile:
        """
        Extract structural information from a .java file using regex.

        Returns a ParsedFile with extraction_mode="regex". Fields that
        cannot be extracted reliably are set to empty lists or None.
        Never raises — unreadable files return a minimal envelope and
        log a WARNING.

        :param java_file:    Absolute path to the .java source file.
        :param corpus_root:  Absolute path to the corpus root directory.
        """
        source_file = java_file.relative_to(corpus_root).as_posix()

        try:
            source = java_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("RegexFallback: cannot read %s — %s", java_file, exc)
            return _empty_envelope(source_file)

        return self._extract(source, source_file)

    # ------------------------------------------------------------------
    # Private orchestration
    # ------------------------------------------------------------------

    def _extract(self, source: str, source_file: str) -> ParsedFile:
        """Run all regex patterns against the source text and assemble a ParsedFile."""
        package = self._extract_package(source)
        imports = self._extract_imports(source)
        kind, simple_name = self._extract_type_decl(source)

        if simple_name is None:
            logger.warning("RegexFallback: no type declaration found in %s", source_file)
            return _empty_envelope(source_file)

        fqcn = f"{package}.{simple_name}" if package else simple_name
        annotations = self._extract_annotations(source)
        stereotype = next((a for a in annotations if a in _STEREOTYPES), None)
        fields = self._extract_fields(source, fqcn)
        methods = self._extract_methods(source, fqcn)

        result: ParsedFile = {
            # --- required base ---
            "kind": kind,
            "id": fqcn,
            "name": simple_name,
            "source_file": source_file,
            "extraction_mode": "regex",
            "annotations": annotations,
            "imports": imports,
            # --- kind-specific: class fields (safe to include for all kinds in
            #     fallback — graph builder checks `kind` anyway) ---
            "modifiers": [],
            "stereotype": stereotype,
            "superclass": None,
            "implements": [],
            "is_inner_class": False,
            "table_name": None,
            "entry_point": "SpringBootApplication" in annotations,
            "fields": fields,
            "methods": methods,
            "wmc": None,
            "cbo": None,
            "lcom4": None,
        }

        # Interface uses extends_interfaces rather than implements
        if kind == "interface":
            result["extends_interfaces"] = []

        return result

    # ------------------------------------------------------------------
    # Private extraction methods
    # ------------------------------------------------------------------

    def _extract_package(self, source: str) -> str:
        """Return the package name, or empty string if absent."""
        match = _RE_PACKAGE.search(source)
        return match.group(1) if match else ""

    def _extract_imports(self, source: str) -> list[str]:
        """Return all import strings (fully qualified, without trailing semicolon)."""
        return _RE_IMPORT.findall(source)

    def _extract_type_decl(self, source: str) -> tuple[str, str | None]:
        """
        Return (kind, simple_name) for the primary type declaration.

        kind is normalised to graph schema values:
          "class" | "interface" | "enum" | "record" | "annotation_type"

        Returns ("class", None) when no declaration is found.
        """
        match = _RE_TYPE_DECL.search(source)
        if not match:
            return "class", None

        raw_kind, simple_name = match.group(1), match.group(2)

        kind_map = {
            "@interface": "annotation_type",
            "interface": "interface",
            "enum": "enum",
            "record": "record",
            "class": "class",
        }
        return kind_map.get(raw_kind, "class"), simple_name

    def _extract_annotations(self, source: str) -> list[str]:
        """
        Extract annotation simple names from the class-level preamble.

        Scans only the text before the primary type declaration keyword
        to avoid picking up method or field annotations in the body.

        Lifted from legacy code_reader._extract_class_annotations and
        categorizer._extract_preamble_annotations — unified here.
        """
        type_match = _RE_TYPE_DECL.search(source)
        preamble = source[: type_match.start()] if type_match else source

        # Preserve declaration order; deduplicate while keeping first occurrence.
        seen: set[str] = set()
        result: list[str] = []
        for name in _RE_ANNOTATION.findall(preamble):
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _extract_fields(self, source: str, fqcn: str) -> list[FieldFact]:
        """
        Extract field declarations from the class body.

        Returns minimal FieldFact objects — type and name only.
        All metadata (is_autowired, injection_type, column, etc.) defaults
        to False / None / [] because field annotations cannot be correlated
        at regex level without an AST.

        Broadened from legacy dependency_extractor._FIELD_RE which only
        matched private final fields.
        """
        facts: list[FieldFact] = []
        for match in _RE_FIELD.finditer(source):
            field_type = match.group(1).strip()
            field_name = match.group(2).strip()

            # Skip obvious false positives: Java keywords, single-char types
            if field_type in _METHOD_KEYWORD_NOISE or len(field_type) < 2:
                continue

            fact: FieldFact = {
                "id": f"{fqcn}.{field_name}",
                "name": field_name,
                "type": field_type,
                "modifiers": [],
                "annotations": [],
                "is_autowired": False,
                "is_id": False,
                "injection_type": None,
                "qualifier": None,
                "generation": None,
                "column": None,
                "constraints": [],
            }
            facts.append(fact)
        return facts

    def _extract_methods(self, source: str, fqcn: str) -> list[MethodFact]:
        """
        Extract method signatures from the class body.

        Returns minimal MethodFact objects — name and return_type only.
        Parameters, HTTP metadata, calls, and complexity are all absent
        because they require body traversal.

        The method id uses "()" with no param types since parameter types
        cannot be recovered reliably from a single-line signature regex.
        """
        facts: list[MethodFact] = []
        for match in _RE_METHOD.finditer(source):
            return_type = match.group(1).strip()
            method_name = match.group(2).strip()

            # Filter Java control-flow keywords that the pattern can mistake for methods
            if return_type in _METHOD_KEYWORD_NOISE or method_name in _METHOD_KEYWORD_NOISE:
                continue

            fact: MethodFact = {
                "id": f"{fqcn}#{method_name}()",
                "name": method_name,
                "return_type": return_type,
                "modifiers": [],
                "annotations": [],
                "is_constructor": False,
                "line_range": [0, 0],
                "parameters": [],
                "is_bean_factory": False,
                "exception_handler": False,
                "response_body": False,
                "response_status": None,
                "http_metadata": None,
                "cyclomatic_complexity": None,
                "cognitive_complexity": None,
                "method_loc": None,
                "calls": [],
            }
            facts.append(fact)
        return facts


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _empty_envelope(source_file: str) -> ParsedFile:
    """
    Minimal ParsedFile for a file that could not be read or parsed at all.
    The graph builder can still record the file's existence in the corpus.
    """
    stem = source_file.rsplit("/", 1)[-1].removesuffix(".java")
    return {
        "kind": "class",
        "id": source_file.replace("/", ".").removesuffix(".java"),
        "name": stem,
        "source_file": source_file,
        "extraction_mode": "regex",
        "annotations": [],
        "imports": [],
    }
