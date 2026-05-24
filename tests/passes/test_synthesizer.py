import json

from codeograph.llm.types import LlmResult, TokenUsage
from codeograph.passes.pass2.schemas import CrossDomainDependency, SynthesisResult
from codeograph.passes.pass2.synthesizer import CorpusSynthesizer


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

    with open(out_path, "r", encoding="utf-8") as fh:
        written = json.load(fh)

    expected_result = synthesis.model_dump()
    assert result == expected_result

    assert written["projectOverview"] == {
        "description": synthesis.description,
        "architecturePattern": synthesis.architecture_pattern,
        "domains": synthesis.domains,
        "crossDomainDependencies": [
            dep.model_dump() for dep in synthesis.cross_domain_dependencies
        ],
    }

    assert written["nodes"] == graph["nodes"]

    assert len(mock_llm_provider.calls) == 1