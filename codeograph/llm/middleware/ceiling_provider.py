import threading
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.models import LlmResult, Message, Tier
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


class CeilingLlmProvider(LlmProvider):
    """LlmProvider wrapper that enforces maximum limit ceilings on calls/tokens."""

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
        """Perform request while checking limits and accumulating counts."""
        # TODO(learner): Implement the mid-run ceiling check and call/token tracking logic:
        # 1. Before making the call, check self._calls_count. If self._max_calls is set
        #    and self._calls_count >= self._max_calls, raise LlmCeilingExceededError.
        # 2. Increment call count.
        # 3. Call inner provider's complete_structured.
        # 4. Extract total tokens (usage.input_tokens + usage.output_tokens) from result.usage.
        # 5. Accumulate into self._tokens_count. If self._max_tokens is set and
        #    self._tokens_count > self._max_tokens, raise LlmCeilingExceededError.
        # 6. Ensure all increments, reads, and checks are thread-safe by using self._lock.
        #    Tip: Raise the exception outside the lock block if possible, but compute inside.

        with self._lock:
            if self._max_calls is not None and self._calls_count >= self._max_calls:
                err = LlmCeilingExceededError(
                    f"LLM call ceiling of {self._max_calls} calls exceeded (current calls: {self._calls_count})"
                )
            else:
                self._calls_count += 1
                err = None

        if err is not None:
            raise err

        result = self._inner.complete_structured(
            tier,
            messages,
            schema,
            override_model=override_model,
            max_tokens=max_tokens,
        )

        total_tokens = result.usage.input_tokens + result.usage.output_tokens

        with self._lock:
            self._tokens_count += total_tokens
            if self._max_tokens is not None and self._tokens_count > self._max_tokens:
                err = LlmCeilingExceededError(
                    f"LLM token ceiling of {self._max_tokens} tokens exceeded (current tokens: {self._tokens_count})"
                )
            else:
                err = None

        if err is not None:
            raise err

        return result