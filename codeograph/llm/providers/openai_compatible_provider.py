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

        # Construct kwargs. We wrap api_key in SecretStr if provided.
        # Otherwise we pass a placeholder key to avoid ChatOpenAI validation errors
        # and prevent it from picking up a default/wrong OPENAI_API_KEY from the environment.
        chat_kwargs = {**kwargs}
        if api_key:
            chat_kwargs["api_key"] = SecretStr(api_key)
        else:
            chat_kwargs["api_key"] = SecretStr("no-key-required")

        if "model" not in chat_kwargs and "model_name" not in chat_kwargs:
            chat_kwargs["model"] = tier_map[Tier.DEEP]

        chat = ChatOpenAI(base_url=base_url, **chat_kwargs)
        super().__init__(chat, tier_map)
