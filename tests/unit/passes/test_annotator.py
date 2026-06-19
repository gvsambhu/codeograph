import json

from codeograph.llm.models import LlmResult, TokenUsage
from codeograph.passes.pass1.models import AnnotationRecord, NodeAnnotation
from codeograph.passes.pass1.node_annotator import NodeAnnotator


def test_annotator_normal_nodes(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "annotations"

    expected_annotation = NodeAnnotation(
        node_id="NodeA",
        class_name="A",
        stereotype="Entity",
        domain_hint="test-domain",
        description="Dummy annotation for class A.",
        methods=[],
    )
    mock_llm_provider.mock_response = LlmResult(
        value=expected_annotation,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    annotator = NodeAnnotator(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
    )

    nodes = [
        {
            "id": "NodeA",
            "name": "A",
            "category": "CLASS",
            "source_code": "class A {}",
            "dependencies": {"injected": []},
        }
    ]

    result = annotator.annotate(nodes)

    out_path = output_dir / "llm-annotations.json"
    assert output_dir.exists()
    assert out_path.is_file()

    with open(out_path, encoding="utf-8") as fh:
        written = json.load(fh)

    # Annotator now wraps each NodeAnnotation in an AnnotationRecord envelope
    # (orchestrator-owned `degraded` separated from the LLM-response schema).
    expected = [
        AnnotationRecord(
            node_id="NodeA",
            degraded=False,
            annotation=expected_annotation,
        ).model_dump()
    ]
    assert result == expected
    assert written == expected


def test_annotator_degraded_nodes(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "annotations"

    annotator = NodeAnnotator(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
    )

    oversized_source = "x" * 120_001
    nodes = [
        {
            "id": "HugeNode",
            "name": "HugeNode",
            "category": "CLASS",
            "source_code": oversized_source,
            "dependencies": {"injected": []},
        }
    ]

    result = annotator.annotate(nodes)

    out_path = output_dir / "llm-annotations.json"
    assert out_path.is_file()

    with open(out_path, encoding="utf-8") as fh:
        written = json.load(fh)

    # Degraded records: the envelope carries the degradation marker; the inner
    # `annotation` is None because the LLM was never called for this node.
    expected = [
        AnnotationRecord(
            node_id="HugeNode",
            degraded=True,
            annotation=None,
        ).model_dump()
    ]

    assert result == expected
    assert written == expected
    assert len(mock_llm_provider.calls) == 0
