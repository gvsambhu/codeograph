from unittest.mock import patch

from pydantic import BaseModel

from codeograph.llm.errors import LlmTransientError
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.middleware.retrying_llm_provider import RetryingLlmProvider
from codeograph.llm.types import LlmResult, Tier, TokenUsage


class DummySchema(BaseModel):
    text: str = "ok"


def test_retry_middleware_success_first_try(mock_llm_provider):
    policy = RetryPolicy(max_attempts=3)
    provider = RetryingLlmProvider(mock_llm_provider, policy)

    result = provider.complete_structured(Tier.FAST, [], DummySchema)

    assert result is not None
    assert len(mock_llm_provider.calls) == 1


def test_retry_middleware_transient_error(mock_llm_provider):
    policy = RetryPolicy(max_attempts=3, initial_backoff_s=0.01)
    provider = RetryingLlmProvider(mock_llm_provider, policy)

    mock_success_result = LlmResult(
        value=DummySchema(text="recovered"),
        usage=TokenUsage(1, 1, 0),
        model="mock",
        latency_ms=1,
    )

    with patch("time.sleep", return_value=None):
        with patch.object(
            mock_llm_provider,
            "complete_structured",
            side_effect=[
                LlmTransientError("Temporary timeout!"),
                mock_success_result,
            ],
        ) as patched_method:
            result = provider.complete_structured(Tier.FAST, [], DummySchema)

    assert result == mock_success_result
    assert patched_method.call_count == 2
