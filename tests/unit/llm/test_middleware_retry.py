from unittest.mock import patch

from pydantic import BaseModel

from codeograph.llm.errors import LlmTransientError
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.middleware.retrying_llm_provider import RetryingLlmProvider
from codeograph.llm.models import LlmResult, Tier, TokenUsage


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


def test_retry_middleware_honors_retry_after_hint(mock_llm_provider):
    """RetryPolicy.respect_retry_after_header (ADR-013 Fork 6) was declared but never
    read before this fix (2026-07-06 manual-run follow-up to MR-03) — a server-supplied
    Retry-After hint should win over the fixed exponential backoff schedule."""
    policy = RetryPolicy(max_attempts=2, initial_backoff_s=0.01, respect_retry_after_header=True)
    provider = RetryingLlmProvider(mock_llm_provider, policy)

    mock_success_result = LlmResult(
        value=DummySchema(text="recovered"),
        usage=TokenUsage(1, 1, 0),
        model="mock",
        latency_ms=1,
    )

    with patch("time.sleep", return_value=None) as sleep_mock:
        with patch.object(
            mock_llm_provider,
            "complete_structured",
            side_effect=[
                LlmTransientError("Rate limited", retry_after_s=38.0),
                mock_success_result,
            ],
        ):
            result = provider.complete_structured(Tier.FAST, [], DummySchema)

    assert result == mock_success_result
    sleep_mock.assert_called_once_with(38.0)


def test_retry_middleware_falls_back_to_backoff_without_retry_after_hint(mock_llm_provider):
    policy = RetryPolicy(max_attempts=2, initial_backoff_s=0.01, respect_retry_after_header=True)
    provider = RetryingLlmProvider(mock_llm_provider, policy)

    mock_success_result = LlmResult(
        value=DummySchema(text="recovered"),
        usage=TokenUsage(1, 1, 0),
        model="mock",
        latency_ms=1,
    )

    with patch("time.sleep", return_value=None) as sleep_mock:
        with patch.object(
            mock_llm_provider,
            "complete_structured",
            side_effect=[
                LlmTransientError("Temporary timeout!"),
                mock_success_result,
            ],
        ):
            result = provider.complete_structured(Tier.FAST, [], DummySchema)

    assert result == mock_success_result
    sleep_mock.assert_called_once_with(0.01)
