import json

import pytest

from codeograph.llm.errors import LlmError
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

    oversized_source = "x" * 240_001
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


def test_annotator_failure_ratio_abort(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "annotations"
    annotator = NodeAnnotator(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
        max_pass1_failure_ratio=0.10,
    )

    nodes = [
        {
            "id": f"Node{i}",
            "name": f"A{i}",
            "category": "CLASS",
            "source_code": f"class A{i} {{}}",
            "dependencies": {"injected": []},
        }
        for i in range(10)
    ]

    # We mock complete_structured_many directly to return exactly 2 errors and 8 successes
    # Or just mock the provider to raise error 2 times
    original_complete = mock_llm_provider.complete_structured
    call_count = [0]

    def _mock_complete(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            raise LlmError("Mock failure")
        return original_complete(*args, **kwargs)

    mock_llm_provider.complete_structured = _mock_complete

    expected_annotation = NodeAnnotation(
        node_id="test",
        class_name="A",
        stereotype="Entity",
        domain_hint="test-domain",
        description="Dummy annotation",
        methods=[],
    )
    mock_llm_provider.mock_response = LlmResult(
        value=expected_annotation,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    with pytest.raises(LlmError, match="exceeds max"):
        annotator.annotate(nodes)


def test_annotator_failure_below_n_floor_abort(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "annotations"
    annotator = NodeAnnotator(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
        max_pass1_failure_ratio=0.10,
    )

    # 9 nodes is below the floor of 10
    nodes = [
        {
            "id": f"Node{i}",
            "name": f"A{i}",
            "category": "CLASS",
            "source_code": f"class A{i} {{}}",
            "dependencies": {"injected": []},
        }
        for i in range(9)
    ]

    original_complete = mock_llm_provider.complete_structured
    call_count = [0]

    def _mock_complete(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 5:  # 5/9 > 0.1 ratio, but more importantly 5 > 3 absolute
            raise LlmError("Mock failure")
        return original_complete(*args, **kwargs)

    mock_llm_provider.complete_structured = _mock_complete

    expected_annotation = NodeAnnotation(
        node_id="test",
        class_name="A",
        stereotype="Entity",
        domain_hint="test-domain",
        description="Dummy annotation",
        methods=[],
    )
    mock_llm_provider.mock_response = LlmResult(
        value=expected_annotation,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    # 5/9 failures exceeds absolute minimum of 3 — should abort
    with pytest.raises(LlmError, match="exceeds absolute minimum"):
        annotator.annotate(nodes)


def test_annotator_failure_below_n_floor_ok(mock_llm_provider, mock_prompt_loader, tmp_path):
    output_dir = tmp_path / "annotations"
    annotator = NodeAnnotator(
        provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        output_dir=output_dir,
        max_pass1_failure_ratio=0.10,
    )

    # 9 nodes is below the floor of 10
    nodes = [
        {
            "id": f"Node{i}",
            "name": f"A{i}",
            "category": "CLASS",
            "source_code": f"class A{i} {{}}",
            "dependencies": {"injected": []},
        }
        for i in range(9)
    ]

    original_complete = mock_llm_provider.complete_structured
    call_count = [0]

    expected_annotation = NodeAnnotation(
        node_id="test",
        class_name="A",
        stereotype="Entity",
        domain_hint="test-domain",
        description="Dummy annotation",
        methods=[],
    )
    mock_llm_provider.mock_response = LlmResult(
        value=expected_annotation,
        usage=TokenUsage(10, 20, 0),
        model="mock-model",
        latency_ms=100,
    )

    def _mock_complete(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:  # 2/9 failures — below absolute minimum of 3
            raise LlmError("Mock failure")
        return original_complete(*args, **kwargs)

    mock_llm_provider.complete_structured = _mock_complete

    records = annotator.annotate(nodes)
    assert len(records) == 9

    degraded_count = sum(1 for r in records if r["degraded"])
    assert degraded_count == 2
