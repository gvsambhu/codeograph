from typing import Any

from langchain_anthropic import ChatAnthropic
from pydantic import SecretStr

from codeograph.llm.providers.langchain_base import LangChainLlmProvider
from codeograph.llm.models import Tier


class AnthropicProvider(LangChainLlmProvider):
    def __init__(self, api_key: str, tier_map: dict[Tier, str], **kwargs: Any) -> None:
        if not api_key:
            raise ValueError("Anthropic API key cannot be empty.")
        if not tier_map:
            raise ValueError("tier_map must map Tiers to model strings.")
        for tier in Tier:
            if tier not in tier_map:
                raise ValueError(f"Missing model mapping for tier: {tier}")

        # ChatAnthropic requires a SecretStr for api_key; wrap the plain string here so
        # callers can pass a raw key without forcing them to import pydantic.
        chat = ChatAnthropic(api_key=SecretStr(api_key), **kwargs)
        super().__init__(chat, tier_map)
