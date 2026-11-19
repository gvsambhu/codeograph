from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from codeograph.llm.models import Tier
from codeograph.llm.providers.langchain_base import LangChainLlmProvider


class OpenAICompatibleProvider(LangChainLlmProvider):
    """Generic LLM provider for any OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        tier_map: dict[Tier, str],
        **kwargs: Any,
    ) -> None:
        if not base_url:
            raise ValueError("Base URL cannot be empty for OpenAI-compatible provider.")
        if not tier_map:
            raise ValueError("tier_map must map Tiers to model strings.")
        for tier in Tier:
            if tier not in tier_map:
                raise ValueError(f"Missing model mapping for tier: {tier}")

        # Wrap api_key in SecretStr if provided. Otherwise pass a placeholder key to avoid
        # ChatOpenAI validation errors and to stop it picking up a default/wrong OPENAI_API_KEY
        # from the environment.
        secret = SecretStr(api_key or "no-key-required")

        def chat_factory(model: str) -> ChatOpenAI:
            return ChatOpenAI(model=model, base_url=base_url, api_key=secret, **kwargs)

        super().__init__(chat_factory, tier_map)
