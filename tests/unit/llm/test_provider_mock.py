from pydantic import BaseModel

from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage


class DummySchema(BaseModel):
    field: str


def test_mock_provider_basic(mock_llm_provider):
    """The mock provider returns the configured response and records the call."""
    messages = [Message(role="user", content="Hello")]
    mock_llm_provider.mock_response = LlmResult(
        value=DummySchema(field="configured value"),
        usage=TokenUsage(input_tokens=10, output_tokens=10, cached_tokens=0),
        model="mock-model",
        latency_ms=100,
    )

    result = mock_llm_provider.complete_structured(tier=Tier.FAST, messages=messages, schema=DummySchema)

    assert result.model == "mock-model"
    assert result.value == DummySchema(field="configured value")
    assert len(mock_llm_provider.calls) == 1
    assert mock_llm_provider.calls[0]["messages"] == messages
