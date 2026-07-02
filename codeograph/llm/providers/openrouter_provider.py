from typing import Any

from codeograph.llm.models import Tier
from codeograph.llm.providers.openai_compatible_provider import OpenAICompatibleProvider

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter-specific LLM provider preset."""

    def __init__(self, api_key: str, tier_map: dict[Tier, str], **kwargs: Any) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key cannot be empty.")
        super().__init__(
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
            tier_map=tier_map,
            **kwargs,
        )
