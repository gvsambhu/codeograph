from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.types import LlmResult, Message, Tier

T = TypeVar("T", bound=BaseModel)


class LlmProvider(ABC):
    @abstractmethod
    def count_tokens(self, messages: list[Message]) -> int:
        """Pre-flight token count."""
        pass

    @abstractmethod
    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        """Return the concrete model string that will be sent to the provider.

        Middleware layers must delegate to their inner provider.  Leaf providers
        look up their tier_map.  Required so CachingLlmProvider can include the
        real model name in the cache key (ADR-015 Fork 4) before the call is made.
        """
        pass

    @abstractmethod
    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        """Complete a single structured output request."""
        pass

    def complete_structured_many(
        self,
        tier: Tier,
        requests: list[tuple[list[Message], type[T]]],
        *,
        max_concurrent: int = 10,
        override_model: str | None = None,
    ) -> list[LlmResult[T]]:
        """Default impl uses ThreadPoolExecutor. Provider-uniform."""
        with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
            futures = [
                ex.submit(self.complete_structured, tier, msgs, schema, override_model=override_model, max_tokens=4096)
                for msgs, schema in requests
            ]
            return [f.result() for f in futures]
