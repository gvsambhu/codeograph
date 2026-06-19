import time
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.errors import LlmRateLimitExhausted, LlmTransientError
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.provider import LlmProvider
from codeograph.llm.models import LlmResult, Message, Tier

T = TypeVar("T", bound=BaseModel)

# Note: For pass-specific retry policies, instantiate different RetryPolicy objects
# in the factory or orchestrator. For example, use max_attempts=1 for FAST passes
# and max_attempts=5 for DEEP synthesis passes where stability is critical.


class RetryingLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, policy: RetryPolicy):
        self._inner = inner
        self._policy = policy

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
        attempts = 0
        backoff = self._policy.initial_backoff_s

        while True:
            attempts += 1
            try:
                return self._inner.complete_structured(
                    tier, messages, schema, override_model=override_model, max_tokens=max_tokens
                )
            except LlmTransientError as e:
                if attempts >= self._policy.max_attempts:
                    raise LlmRateLimitExhausted(f"Exhausted {self._policy.max_attempts} attempts.") from e

                time.sleep(backoff)
                backoff = min(backoff * self._policy.backoff_multiplier, self._policy.max_backoff_s)
