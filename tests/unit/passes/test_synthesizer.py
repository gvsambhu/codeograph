import json

from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph
from codeograph.llm.models import LlmResult, TokenUsage
from codeograph.passes.pass2.corpus_synthesizer import CorpusSynthesizer
from codeograph.passes.pass2.models import CrossDomainDependency, SynthesisResult


def test_synthesizer_output_validates_against_graph_schema(mock_llm_provider, mock_prompt_loader, tmp_path):
    """MR-07 (2026-07-06 manual run): graph.schema.json never declared 'projectOverview',
    so any graph.json enriched by Pass 2 failed CodeographKnowledgeGraph.model_validate —
    which `codeograph render` performs on every load. This exercises the exact dict shape
    corpus_synthesizer.py writes against a minimal-but-schema-conformant graph."""
    output_dir = tmp_path / "pass2"

    annotations: list[dict[str, object]] = []
    graph: dict[str, object] = {"nodes": [], "edges": []}

    synthesis = SynthesisResult(
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

    mock_llm_provider.mock_response = LlmResult(
        value=synthesis,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    synthesizer = CorpusSynthesizer(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
    )
    synthesizer.synthesize(annotations, graph)

    with open(output_dir / "graph.json", encoding="utf-8") as fh:
        written = json.load(fh)

    validated = CodeographKnowledgeGraph.model_validate(written)
    assert validated.projectOverview is not None
    assert validated.projectOverview.description == synthesis.description
    assert len(validated.projectOverview.crossDomainDependencies) == 1


def test_synthesizer_basic(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "pass2"

    annotations = [
        {
            "node_id": "NodeA",
            "degraded": False,
            "class_name": "A",
            "stereotype": "SERVICE",
            "domain_hint": "billing",
            "description": "Handles billing operations.",
            "methods": [],
        }
    ]
    graph = {
        "nodes": [
            {
                "id": "NodeA",
                "name": "A",
                "category": "CLASS",
            }
        ]
    }

    synthesis = SynthesisResult(
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

    mock_llm_provider.mock_response = LlmResult(
        value=synthesis,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    synthesizer = CorpusSynthesizer(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
    )

    result = synthesizer.synthesize(annotations, graph)

    out_path = output_dir / "graph.json"
    assert out_path.is_file()

    with open(out_path, encoding="utf-8") as fh:
        written = json.load(fh)

    expected_result = synthesis.model_dump()
    assert result == expected_result

    assert written["projectOverview"] == {
        "description": synthesis.description,
        "architecturePattern": synthesis.architecture_pattern,
        "domains": synthesis.domains,
        "crossDomainDependencies": [dep.model_dump() for dep in synthesis.cross_domain_dependencies],
    }

    assert written["nodes"] == graph["nodes"]

    assert len(mock_llm_provider.calls) == 1
