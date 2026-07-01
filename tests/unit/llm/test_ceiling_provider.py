import pytest
from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.middleware.ceiling_llm_provider import CeilingLlmProvider
from codeograph.llm.models import Message, Tier
from tests.fixtures.llm.mock_provider import MockLlmProviderBuilder


class MockSchema(BaseModel):
    name: str


def test_ceiling_provider_under_threshold():
    """Verify that CeilingLlmProvider proceeds if limits are not exceeded."""
    inner = MockLlmProviderBuilder().with_response({"name": "test"}).build()
    provider = CeilingLlmProvider(inner, max_calls=2, max_tokens=100)

    res = provider.complete_structured(
        Tier.FAST, [Message(role="user", content="hello")], MockSchema
    )

    assert res.value.name == "test"
    assert provider._calls_count == 1
    expected_tokens = res.usage.input_tokens + res.usage.output_tokens
    assert provider._tokens_count == expected_tokens

def test_ceiling_provider_exceeds_calls():
    """Verify that CeilingLlmProvider aborts when max calls are exceeded."""
    inner = (
        MockLlmProviderBuilder()
        .with_response({"name": "test1"})
        .with_response({"name": "test2"})
        .build()
    )
    provider = CeilingLlmProvider(inner, max_calls=1)

    # First call should succeed
    provider.complete_structured(
        Tier.FAST, [Message(role="user", content="hello")], MockSchema
    )

    # Second call should exceed calls and raise LlmCeilingExceededError
    with pytest.raises(LlmCeilingExceededError) as exc_info:
        provider.complete_structured(
            Tier.FAST, [Message(role="user", content="hello")], MockSchema
        )
    assert "call" in str(exc_info.value).lower()

def test_ceiling_provider_exceeds_tokens():
    """Verify that CeilingLlmProvider aborts when max tokens are exceeded."""
    inner = (
        MockLlmProviderBuilder()
        .with_response({"name": "test1"})
        .with_response({"name": "test2"})
        .build()
    )
    provider = CeilingLlmProvider(inner, max_tokens=15)

    # Depending on implementation: first call may raise LlmCeilingExceededError immediately,
    # or the second call will trigger it.
    try:
        provider.complete_structured(
            Tier.FAST, [Message(role="user", content="hello")], MockSchema
        )
        # If first call succeeded, second call must raise the exception
        with pytest.raises(LlmCeilingExceededError) as exc_info:
            provider.complete_structured(
                Tier.FAST, [Message(role="user", content="hello")], MockSchema
            )
        assert "token" in str(exc_info.value).lower()
    except LlmCeilingExceededError as e:
        assert "token" in str(e).lower()