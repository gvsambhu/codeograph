from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from codeograph.llm.models import Tier
from codeograph.llm.providers.langchain_base import LangChainLlmProvider

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(LangChainLlmProvider):
    def __init__(self, api_key: str, tier_map: dict[Tier, str], **kwargs: Any) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key cannot be empty.")
        if not tier_map:
            raise ValueError("tier_map must map Tiers to model strings.")
        for tier in Tier:
            if tier not in tier_map:
                raise ValueError(f"Missing model mapping for tier: {tier}")

        chat = ChatOpenAI(api_key=SecretStr(api_key), base_url=_OPENROUTER_BASE_URL, **kwargs)
        super().__init__(chat, tier_map)
