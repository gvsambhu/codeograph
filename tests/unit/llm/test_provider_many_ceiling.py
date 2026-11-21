"""A spend ceiling ends a ``complete_structured_many`` batch instead of counting as one more failure."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.middleware.ceiling_llm_provider import CeilingLlmProvider
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


class _Schema(BaseModel):
    name: str = "ok"


class _CeilingAfterProvider(LlmProvider):
    """Succeeds for ``succeed`` calls, then raises the ceiling error on every call after that."""

    def __init__(self, succeed: int) -> None:
        self.succeed = succeed
        self.calls = 0
        self._lock = threading.Lock()

    def count_tokens(self, messages: list[Message]) -> int:
        return 1

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return "m"

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
            number = self.calls
        if number > self.succeed:
            raise LlmCeilingExceededError("ceiling reached")
        return LlmResult(
            value=schema.model_construct(),
            usage=TokenUsage(input_tokens=1, output_tokens=1, cached_tokens=0),
            model="m",
            latency_ms=1,
        )


def _requests(n: int) -> list[tuple[list[Message], type[_Schema]]]:
    return [([Message(role="user", content=f"req{i}")], _Schema) for i in range(n)]


def test_a_ceiling_stops_the_batch_without_starting_queued_calls() -> None:
    provider = _CeilingAfterProvider(succeed=3)

    results = provider.complete_structured_many(Tier.FAST, _requests(10), max_concurrent=1)

    assert provider.calls == 4, "the call that hit the ceiling is the last one started"
    assert [isinstance(r, LlmResult) for r in results] == [True] * 3 + [False] * 7
    assert all(isinstance(r, LlmCeilingExceededError) for r in results[3:])


class _ForcedRaceProvider(LlmProvider):
    """Two running calls raise the ceiling together while later requests remain queued."""

    def __init__(self) -> None:
        self.calls = 0
        self.calls_after_ceiling = 0
        self.queued_call_started = threading.Event()
        self._ceiling_raised = threading.Event()
        self._running = threading.Barrier(2)
        self._lock = threading.Lock()

    def count_tokens(self, messages: list[Message]) -> int:
        return 1

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return "m"

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
            number = self.calls
            if self._ceiling_raised.is_set():
                self.calls_after_ceiling += 1
            if number == 3:
                self.queued_call_started.set()

        if number <= 2:
            self._running.wait(timeout=5)
            self._ceiling_raised.set()
            raise LlmCeilingExceededError("ceiling reached")

        return LlmResult(
            value=schema.model_construct(),
            usage=TokenUsage(input_tokens=1, output_tokens=1, cached_tokens=0),
            model="m",
            latency_ms=1,
        )


class _HeldRequests(list[tuple[list[Message], type[_Schema]]]):
    """Keeps the batch's submission step occupied while the running calls finish."""

    def __init__(self, provider: _ForcedRaceProvider) -> None:
        super().__init__(_requests(10))
        self._provider = provider

    def __iter__(self) -> Iterator[tuple[list[Message], type[_Schema]]]:
        yield from super().__iter__()
        self._provider.queued_call_started.wait(timeout=0.05)


def test_a_forced_ceiling_race_never_starts_a_queued_call() -> None:
    provider = _ForcedRaceProvider()

    results = provider.complete_structured_many(Tier.FAST, _HeldRequests(provider), max_concurrent=2)

    assert provider.calls == 2
    assert provider.calls_after_ceiling == 0
    assert len(results) == 10
    assert all(isinstance(r, LlmCeilingExceededError) for r in results)


def test_calls_that_finished_before_the_ceiling_keep_their_results_under_concurrency() -> None:
    inner = _CeilingAfterProvider(succeed=3)
    provider = CeilingLlmProvider(inner, max_calls=3)

    results = provider.complete_structured_many(Tier.FAST, _requests(20), max_concurrent=5)

    assert inner.calls == 3
    assert sum(isinstance(r, LlmResult) for r in results) == 3
    assert sum(isinstance(r, LlmCeilingExceededError) for r in results) == 17
