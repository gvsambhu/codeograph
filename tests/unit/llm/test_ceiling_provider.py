import pytest
from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.middleware.ceiling_provider import CeilingLlmProvider
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
    # TODO(learner): Add assertions to verify:
    # 1. res.value.name is "test"
    # 2. provider._calls_count is incremented to 1.
    # 3. provider._tokens_count is incremented by input + output tokens.
    _ = res


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
    # TODO(learner): Assert that the exception message indicates call limit exceeded.
    _ = exc_info


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
        _ = exc_info
    except LlmCeilingExceededError as e:
        # If first call raised it immediately
        # TODO(learner): Assert that the exception message indicates token limit exceeded.
        _ = e
