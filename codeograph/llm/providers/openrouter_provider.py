from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.models import LlmResult, Message, Tier
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


class OpenRouterProvider(LlmProvider):
    # TODO(learner): implement OpenRouter provider (DC2-01)

    def __init__(self, api_key: str, tier_map: dict[Tier, str]) -> None:
        self._api_key = api_key
        self._tier_map = tier_map

    def count_tokens(self, messages: list[Message]) -> int:
        raise NotImplementedError("OpenRouter provider not yet implemented.")

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or self._tier_map[tier]

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        raise NotImplementedError("OpenRouter provider not yet implemented.")
