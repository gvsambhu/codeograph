import threading
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.models import LlmResult, Message, Tier
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


class CeilingLlmProvider(LlmProvider):
    """LlmProvider wrapper that enforces maximum limit ceilings on calls/tokens.

    Both ceilings are checked **before** a call is made (ADR-027 Fork 1: the run aborts when a bound
    *would* be exceeded), so a refused call costs nothing. The token ceiling projects a call's spend as
    its input tokens plus the output cap it runs under, and holds that projection against the budget while
    the call is in flight, so concurrent calls cannot all pass the check. When the call returns, the
    projection is replaced by the tokens it actually used. A result that was paid for is always returned.
    """

    def __init__(
        self,
        inner: LlmProvider,
        max_calls: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._inner = inner
        self._max_calls = max_calls
        self._max_tokens = max_tokens
        self._calls_count = 0
        self._tokens_count = 0
        self._tokens_reserved = 0
        self._lock = threading.Lock()

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return self._inner.resolve_model(tier, override_model)

    def count_tokens(self, messages: list[Message]) -> int:
        return self._inner.count_tokens(messages)

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        """Refuse the call if it would pass a ceiling; otherwise make it and record what it used."""

        # Counting may call out to the provider, so it happens outside the lock.
        projected = self._inner.count_tokens(messages) + max_tokens if self._max_tokens is not None else 0

        with self._lock:
            if self._max_calls is not None and self._calls_count >= self._max_calls:
                raise LlmCeilingExceededError(
                    f"LLM call ceiling of {self._max_calls} calls reached (calls made: {self._calls_count})"
                )
            if self._max_tokens is not None:
                committed = self._tokens_count + self._tokens_reserved
                if committed + projected > self._max_tokens:
                    raise LlmCeilingExceededError(
                        f"LLM token ceiling of {self._max_tokens} tokens would be exceeded "
                        f"(tokens used so far: {committed}; this call needs up to {projected})"
                    )
                self._tokens_reserved += projected
            self._calls_count += 1

        try:
            result = self._inner.complete_structured(
                tier,
                messages,
                schema,
                override_model=override_model,
                max_tokens=max_tokens,
            )
        except BaseException:
            # A failed call returns no usage, so retain its full projection as the conservative spend.
            with self._lock:
                self._tokens_reserved -= projected
                self._tokens_count += projected
            raise

        with self._lock:
            self._tokens_reserved -= projected
            self._tokens_count += result.usage.input_tokens + result.usage.output_tokens

        return result
