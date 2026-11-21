"""CeilingLlmProvider refuses a call that would pass a ceiling, before the call is made.

The inner provider is a real ``LlmProvider`` subclass that counts the calls it receives and reports a
fixed usage per call, so each assertion is about calls actually reaching (or not reaching) the provider.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

import pytest
from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError, LlmError
from codeograph.llm.middleware.ceiling_llm_provider import CeilingLlmProvider
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider


class _Schema(BaseModel):
    name: str


T = TypeVar("T", bound=BaseModel)


class _CountingProvider(LlmProvider):
    """Counts the calls that reach it; each reports ``spend`` total tokens (half in, half out)."""

    def __init__(self, spend: int, prompt_tokens: int = 100, error: Exception | None = None) -> None:
        self.spend = spend
        self.prompt_tokens = prompt_tokens
        self.error = error
        self.calls = 0
        self._lock = threading.Lock()

    def count_tokens(self, messages: list[Message]) -> int:
        return self.prompt_tokens

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or "counting-model"

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        with self._lock:
            self.calls += 1
        if self.error is not None:
            raise self.error
        usage = TokenUsage(input_tokens=self.spend // 2, output_tokens=self.spend - self.spend // 2, cached_tokens=0)
        return LlmResult(value=schema.model_validate({"name": "ok"}), usage=usage, model="counting-model", latency_ms=1)


_MSGS = [Message(role="user", content="hello")]


def _call(provider: CeilingLlmProvider, max_tokens: int = 1_000) -> LlmResult[_Schema]:
    return provider.complete_structured(Tier.FAST, _MSGS, _Schema, max_tokens=max_tokens)


def test_calls_under_both_ceilings_proceed_and_are_tallied() -> None:
    inner = _CountingProvider(spend=1_000)
    provider = CeilingLlmProvider(inner, max_calls=3, max_tokens=10_000)

    result = _call(provider)

    assert result.value.name == "ok"
    assert inner.calls == 1
    assert provider._calls_count == 1
    assert provider._tokens_count == 1_000
    assert provider._tokens_reserved == 0


def test_the_call_ceiling_refuses_before_the_inner_call() -> None:
    inner = _CountingProvider(spend=10)
    provider = CeilingLlmProvider(inner, max_calls=2)

    _call(provider)
    _call(provider)
    with pytest.raises(LlmCeilingExceededError) as exc_info:
        _call(provider)

    assert inner.calls == 2
    assert "call ceiling of 2" in str(exc_info.value)


def test_the_token_ceiling_makes_exactly_the_calls_that_fit_and_drops_no_result() -> None:
    # Each call is projected at 100 prompt + 1,000 cap = 1,100 and uses 2,000. With M = 5,000 the first
    # (0 + 1,100) and second (2,000 + 1,100) fit; the third (4,000 + 1,100 = 5,100) would pass M and is refused.
    inner = _CountingProvider(spend=2_000)
    provider = CeilingLlmProvider(inner, max_tokens=5_000)

    results = [_call(provider), _call(provider)]
    with pytest.raises(LlmCeilingExceededError) as exc_info:
        _call(provider)

    assert all(r.value.name == "ok" for r in results)
    assert inner.calls == 2, "the refused call must not reach the provider"
    assert provider._tokens_count == 4_000
    message = str(exc_info.value)
    assert "token ceiling of 5000" in message
    assert "4000" in message


def test_a_call_that_overruns_its_projection_is_still_returned() -> None:
    # The call uses more than the ceiling; its result was paid for, so it is returned, and the next call is refused.
    inner = _CountingProvider(spend=9_000)
    provider = CeilingLlmProvider(inner, max_tokens=5_000)

    result = _call(provider, max_tokens=500)

    assert result.value.name == "ok"
    assert provider._tokens_count == 9_000
    with pytest.raises(LlmCeilingExceededError):
        _call(provider, max_tokens=500)
    assert inner.calls == 1


def test_a_call_whose_own_projection_exceeds_the_ceiling_is_refused_untouched() -> None:
    inner = _CountingProvider(spend=10, prompt_tokens=400)
    provider = CeilingLlmProvider(inner, max_tokens=1_000)

    with pytest.raises(LlmCeilingExceededError):
        _call(provider, max_tokens=700)

    assert inner.calls == 0
    assert provider._calls_count == 0


def test_a_failed_call_counts_its_reservation_as_spent() -> None:
    inner = _CountingProvider(spend=10, error=LlmError("boom"))
    provider = CeilingLlmProvider(inner, max_tokens=2_000)

    with pytest.raises(LlmError, match="boom"):
        _call(provider)
    with pytest.raises(LlmCeilingExceededError, match="token ceiling of 2000"):
        _call(provider)

    assert inner.calls == 1, "the second call fits only if the failed call's spend is discarded"
    assert provider._tokens_reserved == 0
    assert provider._tokens_count == 1_100


def test_concurrent_callers_never_commit_more_than_the_ceiling() -> None:
    # Each call is projected at 1,100 and uses 1,000. Ten threads race on a 5,000-token ceiling:
    # at most four can be admitted (4 x 1,100 = 4,400; a fifth would project 5,500).
    inner = _CountingProvider(spend=1_000)
    provider = CeilingLlmProvider(inner, max_tokens=5_000)
    start = threading.Barrier(10)

    def attempt() -> bool:
        start.wait()
        try:
            _call(provider)
            return True
        except LlmCeilingExceededError:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        admitted = [f.result() for f in [pool.submit(attempt) for _ in range(10)]]

    assert sum(admitted) == 4
    assert inner.calls == 4
    assert provider._tokens_count == 4_000
    assert provider._tokens_count <= 5_000
