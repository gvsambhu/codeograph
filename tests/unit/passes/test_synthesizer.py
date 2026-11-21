import json

import jsonschema

from codeograph.llm.models import LlmResult, TokenUsage
from codeograph.passes.pass2.corpus_synthesizer import (
    CORPUS_SYNTHESIS_FILENAME,
    CORPUS_SYNTHESIS_SCHEMA_VERSION,
    CorpusSynthesizer,
)
from codeograph.passes.pass2.models import CrossDomainDependency, SynthesisResult

_SCHEMA_PATH = "codeograph/schema/corpus-synthesis.schema.json"


def _synthesis() -> SynthesisResult:
    return SynthesisResult(
        description="A billing-focused service application.",
        architecture_pattern="Layered Monolith",
        domains=["billing", "shared"],
        cross_domain_dependencies=[
            CrossDomainDependency(
                from_class="com.example.billing.A",
                from_domain="billing",
                to_class="com.example.shared.Util",
                to_domain="shared",
                dependency_type="injected_field",
            )
        ],
    )


def _synthesizer(mock_llm_provider, mock_prompt_loader, output_dir, synthesis: SynthesisResult) -> CorpusSynthesizer:
    mock_llm_provider.mock_response = LlmResult(
        value=synthesis,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )
    return CorpusSynthesizer(provider=mock_llm_provider, prompt_loader=mock_prompt_loader, output_dir=output_dir)


def test_synthesizer_writes_only_its_own_file(mock_llm_provider, mock_prompt_loader, tmp_path):
    """Pass 2 writes corpus-synthesis.json and nothing else: the graph and the annotations
    the earlier passes wrote are left byte-for-byte as they were."""
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    graph_bytes = b'{"edges":[],"nodes":[]}\n'
    annotations_bytes = b'[{"node_id": "NodeA", "degraded": false}]'
    (output_dir / "graph.json").write_bytes(graph_bytes)
    (output_dir / "llm-annotations.json").write_bytes(annotations_bytes)

    synthesizer = _synthesizer(mock_llm_provider, mock_prompt_loader, output_dir, _synthesis())
    synthesizer.synthesize([])

    assert sorted(p.name for p in output_dir.iterdir()) == [
        "corpus-synthesis.json",
        "graph.json",
        "llm-annotations.json",
    ]
    assert (output_dir / "graph.json").read_bytes() == graph_bytes
    assert (output_dir / "llm-annotations.json").read_bytes() == annotations_bytes


def test_synthesizer_does_not_create_a_graph(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "out"

    synthesizer = _synthesizer(mock_llm_provider, mock_prompt_loader, output_dir, _synthesis())
    synthesizer.synthesize([])

    assert not (output_dir / "graph.json").exists()
    assert (output_dir / CORPUS_SYNTHESIS_FILENAME).is_file()


def test_synthesizer_output_validates_against_published_schema(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "out"
    synthesis = _synthesis()

    synthesizer = _synthesizer(mock_llm_provider, mock_prompt_loader, output_dir, synthesis)
    synthesizer.synthesize([])

    with open(output_dir / CORPUS_SYNTHESIS_FILENAME, encoding="utf-8") as fh:
        written = json.load(fh)
    with open(_SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)

    jsonschema.validate(written, schema)
    assert written["schema_version"] == CORPUS_SYNTHESIS_SCHEMA_VERSION == "1.0.0"
    assert {k: v for k, v in written.items() if k != "schema_version"} == synthesis.model_dump()


def test_synthesizer_returns_result_and_calls_provider_once(mock_llm_provider, mock_prompt_loader, tmp_path):
    annotations = [
        {
            "node_id": "NodeA",
            "degraded": False,
            "annotation": {
                "class_name": "A",
                "stereotype": "SERVICE",
                "domain_hint": "billing",
                "description": "Handles billing operations.",
            },
        }
    ]
    synthesis = _synthesis()

    synthesizer = _synthesizer(mock_llm_provider, mock_prompt_loader, tmp_path / "out", synthesis)
    result = synthesizer.synthesize(annotations)

    assert result == synthesis.model_dump()
    assert len(mock_llm_provider.calls) == 1
