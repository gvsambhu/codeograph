"""
Golden-graph regression tests (ADR-007).

Surgical codeograph-corpus fixture
====================================
Builds a CorpusSpec from the checked-in fixture at
``tests/fixtures/codeograph-corpus/`` and runs the full CorpusAnalyzer
pipeline.

Normal run
  pytest -m slow
  → graph.json output is compared byte-for-byte against the stored golden.

Update run (after a deliberate graph-schema change)
  pytest tests/integration/test_goldens.py --update-goldens
  or: make golden-update
  → stored golden files are overwritten; diff the result before committing.

Tier 2 (PetClinic) and Tier 3 (JHipster scale) are deferred to v1.1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codeograph.analyzer.corpus_analyzer import CorpusAnalyzer
from codeograph.graph.graph_assembler import GraphAssembler
from codeograph.graph.graph_builder import GraphBuilder
from codeograph.graph.graph_writer import GraphWriter
from codeograph.input.models import AcquisitionSource, BuildTool, CorpusSpec, ModuleSpec
from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
from codeograph.parser.java_file_parser import JavaFileParser
from codeograph.parser.regex_fallback import RegexFallback

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).parent
_FIXTURE_DIR = _TESTS_DIR.parent / "fixtures" / "codeograph-corpus"
_GOLDENS_DIR = _TESTS_DIR.parent / "golden" / "codeograph-corpus"

_CORE_SRC = _FIXTURE_DIR / "module-core" / "src" / "main" / "java"
_WEB_SRC = _FIXTURE_DIR / "module-web" / "src" / "main" / "java"


# ---------------------------------------------------------------------------
# Corpus construction
# ---------------------------------------------------------------------------


def _build_corpus() -> CorpusSpec:
    """Construct CorpusSpec explicitly — surgical, no SourceDiscoverer."""
    core_pkg = _CORE_SRC / "io" / "codeograph" / "corpus" / "core"
    web_pkg = _WEB_SRC / "io" / "codeograph" / "corpus" / "web"

    core_module = ModuleSpec(
        module_id="mod:module-core",
        name="module-core",
        root_path=_FIXTURE_DIR / "module-core",
        build_tool=BuildTool.MAVEN,
        source_roots=[_CORE_SRC],
        pom_path=_FIXTURE_DIR / "module-core" / "pom.xml",
        java_files=[
            core_pkg / "Address.java",
            core_pkg / "Displayable.java",
            core_pkg / "Malformed.java",
            core_pkg / "Order.java",
            core_pkg / "OrderService.java",
            core_pkg / "OrderStatus.java",
            core_pkg / "PageRequest.java",
        ],
    )

    web_module = ModuleSpec(
        module_id="mod:module-web",
        name="module-web",
        root_path=_FIXTURE_DIR / "module-web",
        build_tool=BuildTool.MAVEN,
        source_roots=[_WEB_SRC],
        pom_path=_FIXTURE_DIR / "module-web" / "pom.xml",
        java_files=[
            web_pkg / "GlobalExceptionHandler.java",
            web_pkg / "OrderController.java",
            web_pkg / "Versioned.java",
        ],
    )

    return CorpusSpec(
        acquisition_source=AcquisitionSource.LOCAL,
        corpus_root=_FIXTURE_DIR,
        modules=[core_module, web_module],
    )


# ---------------------------------------------------------------------------
# Golden assertion helper
# ---------------------------------------------------------------------------


def _assert_golden(actual_bytes: bytes, golden_path: Path, *, update: bool) -> None:
    """
    Compare actual_bytes against the stored golden at golden_path.

    If ``update=True``, overwrite the stored golden and pass unconditionally.
    If the golden does not exist and ``update=False``, fail with an actionable
    message directing the developer to run ``pytest --update-goldens``.
    """
    if update:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(actual_bytes)
    else:
        if not golden_path.exists():
            raise AssertionError(
                f"No golden at {golden_path} — run "
                "'pytest tests/integration/test_goldens.py --update-goldens' to capture it."
            )
        expected_bytes = golden_path.read_bytes()
        if actual_bytes != expected_bytes:
            actual_str = actual_bytes.decode("utf-8")
            expected_str = expected_bytes.decode("utf-8")
            import json
            try:
                actual_json = json.loads(actual_str)
                expected_json = json.loads(expected_str)
                actual_formatted = json.dumps(actual_json, indent=2, ensure_ascii=False)
                expected_formatted = json.dumps(expected_json, indent=2, ensure_ascii=False)
            except Exception:
                actual_formatted = actual_str
                expected_formatted = expected_str
            assert actual_formatted == expected_formatted, "Golden graph byte-mismatch detected!"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_tier1_golden(update_goldens: bool, tmp_path: Path) -> None:
    """
    End-to-end golden test: codeograph-corpus fixture → graph.json must
    match the stored golden byte-for-byte.

    Uses real FileParserDispatcher (AST with regex fallback), GraphBuilder,
    GraphAssembler, and GraphWriter — no mocks.
    """
    corpus = _build_corpus()

    try:
        java_parser = JavaFileParser()
    except OSError as exc:
        pytest.skip(f"JVM not available ({exc}) — run in an environment with Java 17+")

    dispatcher = FileParserDispatcher(
        java_parser=java_parser,
        fallback=RegexFallback(),
    )
    analyzer = CorpusAnalyzer(
        dispatcher=dispatcher,
        builder=GraphBuilder(),
        assembler=GraphAssembler(),
        writer=GraphWriter(),
    )

    analyzer.analyze(corpus, tmp_path)
    graph_bytes = (tmp_path / "graph.json").read_bytes()

    _assert_golden(
        graph_bytes,
        _GOLDENS_DIR / "graph.json",
        update=update_goldens,
    )
