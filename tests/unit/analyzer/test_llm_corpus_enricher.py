import json
from typing import Any
from unittest.mock import MagicMock, patch

from codeograph.analyzer.llm_corpus_enricher import LlmCorpusEnricher
from codeograph.config.settings import Settings
from codeograph.llm.models import LlmResult, TokenUsage
from codeograph.manifest.artefact import GraphArtefact
from codeograph.passes.pass1.models import NodeAnnotation
from codeograph.passes.pass1.node_annotator import NodeAnnotator
from codeograph.passes.pass2.models import SynthesisResult
from codeograph.telemetry.session_manager import TelemetrySessionManager
from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator


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
        with patch(
            "codeograph.passes.pass2.corpus_synthesizer.CorpusSynthesizer.synthesize",
            return_value=synthesis.model_dump(),
        ):
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
