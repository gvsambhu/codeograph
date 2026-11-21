import hashlib
import json
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest

from codeograph.analyzer.llm_corpus_enricher import LlmCorpusEnricher
from codeograph.config.settings import Settings
from codeograph.llm.models import LlmResult, TokenUsage
from codeograph.manifest.artefact import GraphArtefact
from codeograph.passes.pass1.models import NodeAnnotation
from codeograph.passes.pass1.node_annotator import NodeAnnotator
from codeograph.passes.pass2.corpus_synthesizer import CORPUS_SYNTHESIS_FILENAME, CorpusSynthesizer
from codeograph.passes.pass2.models import SynthesisResult
from codeograph.telemetry.session_manager import TelemetrySessionManager
from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator


def _writing_synthesize(synthesis: SynthesisResult):
    """Stand-in for ``CorpusSynthesizer.synthesize`` that writes the file the real one writes."""

    def synthesize(self: CorpusSynthesizer, records: list[dict[str, Any]]) -> dict[str, Any]:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": "1.0.0", **synthesis.model_dump()}
        (self._output_dir / CORPUS_SYNTHESIS_FILENAME).write_text(json.dumps(document), encoding="utf-8")
        return synthesis.model_dump()

    return synthesize


def test_enrich_filters_to_class_nodes_and_loads_real_source(tmp_path, mock_llm_provider):
    """MR-12/13 (2026-07-06 manual run): before this fix, `enrich()` sent every graph
    node (methods, fields, modules included) to Pass 1 with an always-empty
    `source_code` — ADR-005 requires one call per class with the real class source.
    This proves both parts land together: only class-kind nodes reach the
    annotator, and the one that does carries real source read from disk."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    (corpus_root / "Foo.java").write_text(
        "public class Foo {\n    void bar() {}\n}\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    graph_data = {
        "nodes": [
            {"id": "Foo", "kind": "class", "name": "Foo", "source_file": "Foo.java", "line_range": [1, 3]},
            {"id": "Foo#bar()", "kind": "method", "name": "bar", "source_file": "Foo.java", "line_range": [2, 2]},
        ],
        "edges": [],
    }
    graph_path = out_dir / "graph.json"
    graph_path.write_text(json.dumps(graph_data), encoding="utf-8")
    graph_artefact = GraphArtefact(path=graph_path, schema_version="2.0.0", sha256="deadbeef")

    settings = Settings(cache_dir=tmp_path / "cache")
    resolver = MagicMock()
    resolver.resolve.return_value = mock_llm_provider

    mock_llm_provider.mock_response = LlmResult(
        value=NodeAnnotation(
            node_id="Foo",
            class_name="Foo",
            stereotype=None,
            domain_hint="test",
            description="A test class.",
            methods=[],
        ),
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=10,
    )

    enricher = LlmCorpusEnricher(
        settings=settings,
        provider_resolver=resolver,
        telemetry_manager=TelemetrySessionManager(settings),
        stats_aggregator=TelemetryStatsAggregator(),
    )

    captured: dict[str, list[dict[str, Any]]] = {}
    original_annotate = NodeAnnotator.annotate

    def spy_annotate(self, nodes):
        captured["nodes"] = nodes
        return original_annotate(self, nodes)

    synthesis = SynthesisResult(
        description="desc",
        architecture_pattern="pattern",
        domains=["test"],
        cross_domain_dependencies=[],
    )

    with patch.object(NodeAnnotator, "annotate", spy_annotate):
        with patch.object(CorpusSynthesizer, "synthesize", _writing_synthesize(synthesis)):
            enricher.enrich(
                corpus_id="test-corpus",
                run_id="run1",
                graph_artefact=graph_artefact,
                out_dir=out_dir,
                corpus_root=corpus_root,
            )

    nodes_seen = captured["nodes"]
    assert len(nodes_seen) == 1
    assert nodes_seen[0]["kind"] == "class"
    assert "void bar()" in nodes_seen[0]["source_code"]


def test_enrich_leaves_graph_untouched_and_returns_both_llm_artefacts(tmp_path, mock_llm_provider):
    """The graph is a function of the corpus alone: enrichment reads it but never rewrites it,
    so the file on disk keeps the bytes the manifest's graph hash describes. Both LLM
    artefacts come back with the sha256 of the bytes on disk and their own schema version."""
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    (corpus_root / "Foo.java").write_text("public class Foo {}\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    graph_data = {
        "nodes": [
            {"id": "Foo", "kind": "class", "name": "Foo", "source_file": "Foo.java", "line_range": [1, 1]},
        ],
        "edges": [],
    }
    graph_path = out_dir / "graph.json"
    graph_path.write_text(json.dumps(graph_data), encoding="utf-8")
    graph_artefact = GraphArtefact(path=graph_path, schema_version="2.0.0", sha256="deadbeef")

    settings = Settings(cache_dir=tmp_path / "cache")
    resolver = MagicMock()
    resolver.resolve.return_value = mock_llm_provider

    mock_llm_provider.mock_response = LlmResult(
        value=NodeAnnotation(
            node_id="Foo",
            class_name="Foo",
            stereotype=None,
            domain_hint="test",
            description="A test class.",
            methods=[],
        ),
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=10,
    )

    enricher = LlmCorpusEnricher(
        settings=settings,
        provider_resolver=resolver,
        telemetry_manager=TelemetrySessionManager(settings),
        stats_aggregator=TelemetryStatsAggregator(),
    )

    graph_bytes_before = graph_path.read_bytes()
    synthesis = SynthesisResult(
        description="d",
        architecture_pattern="p",
        domains=["test"],
        cross_domain_dependencies=[],
    )

    with patch.object(CorpusSynthesizer, "synthesize", _writing_synthesize(synthesis)):
        annotations_artefact, synthesis_artefact, _ = enricher.enrich(
            corpus_id="test-corpus",
            run_id="run1",
            graph_artefact=graph_artefact,
            out_dir=out_dir,
            corpus_root=corpus_root,
        )

    assert graph_path.read_bytes() == graph_bytes_before
    assert "projectOverview" not in graph_path.read_text(encoding="utf-8")

    assert annotations_artefact.path == out_dir / "llm-annotations.json"
    assert synthesis_artefact.path == out_dir / CORPUS_SYNTHESIS_FILENAME
    assert synthesis_artefact.schema_version == "1.0.0"
    assert synthesis_artefact.sha256 == hashlib.sha256(synthesis_artefact.path.read_bytes()).hexdigest()


def test_written_file_artefact_carries_path_version_and_hash(tmp_path):
    written = tmp_path / "corpus-synthesis.json"
    written.write_bytes(b'{"schema_version": "1.0.0"}')

    artefact = LlmCorpusEnricher._artefact_of_written_file(
        written, schema_version="1.0.0", label="corpus synthesis file"
    )

    assert artefact.path == written
    assert artefact.schema_version == "1.0.0"
    assert artefact.sha256 == hashlib.sha256(written.read_bytes()).hexdigest()


def test_missing_written_file_is_a_producer_bug(tmp_path):
    missing = tmp_path / "corpus-synthesis.json"

    with pytest.raises(click.ClickException) as excinfo:
        LlmCorpusEnricher._artefact_of_written_file(missing, schema_version="1.0.0", label="corpus synthesis file")

    message = excinfo.value.message
    assert "wrote no corpus synthesis file" in message
    assert str(missing) in message
    assert "producer bug" in message
