import json

from pydantic import BaseModel

from codeograph.llm.middleware.telemetry_llm_provider import TelemetryLlmProvider
from codeograph.llm.types import CallContext, LlmResult, Message, Purpose, Tier, TokenUsage


class DummySchema(BaseModel):
    text: str


def test_telemetry_middleware_emits_record(mock_llm_provider, tmp_telemetry_jsonl, tmp_path):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")

    provider = TelemetryLlmProvider(mock_llm_provider, tmp_telemetry_jsonl, ctx)

    mock_llm_provider.mock_response = LlmResult(
        value=DummySchema(text="hello"),
        usage=TokenUsage(
            input_tokens=10,
            output_tokens=20,
            cached_tokens=0,
            input_estimated=None,
        ),
        model="mock-model",
        latency_ms=123,
    )

    result = provider.complete_structured(
        Tier.FAST,
        [Message(role="user", content="Hello")],
        DummySchema,
    )

    assert result == mock_llm_provider.mock_response

    jsonl_path = tmp_path / "telemetry" / "test_telemetry.jsonl"
    with open(jsonl_path, encoding="utf-8") as f:
        line = f.readline()

    assert line.strip() != ""

    parsed = json.loads(line)

    assert parsed["prompt_id"] == "test_prompt"
    assert parsed["prompt_version"] == "v1"
    assert parsed["prompt_content_hash"] == "hash"
    assert parsed["corpus_id"] == "corpus"

    assert parsed["tier"] == "fast"
    assert parsed["purpose"] == "annotate"
    assert parsed["model"] == "mock-model"
    assert parsed["override_model"] is None

    assert parsed["input_tokens"] == 10
    assert parsed["output_tokens"] == 20
    assert parsed["cached_tokens"] == 0
    assert parsed["input_estimated"] is None

    assert parsed["status"] == "success"
    assert parsed["error_class"] is None
    assert parsed["error_message"] is None

    assert isinstance(parsed["total_latency_ms"], int)
    assert parsed["total_latency_ms"] >= 0

    assert isinstance(parsed["cost_usd_est"], (int, float))
    assert parsed["cost_usd_est"] == 0.0

    assert parsed["attempts"] == []
