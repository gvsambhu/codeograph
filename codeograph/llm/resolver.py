"""
LlmProviderResolver — resolves and instantiates the configured LLM provider subclass.
"""

from __future__ import annotations

from codeograph.config.settings import Settings
from codeograph.llm.models import ProviderType, Tier
from codeograph.llm.provider import LlmProvider
from codeograph.llm.providers.anthropic_provider import AnthropicProvider
from codeograph.llm.providers.openrouter_provider import OpenRouterProvider


class LlmProviderResolver:
    """Resolves and instantiates the configured LLM provider subclass."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self) -> LlmProvider:
        # Base Provider — dispatches on settings.llm_provider
        tier_map = {
            Tier.FAST: self._settings.llm_model_fast or self._settings.llm_model,
            Tier.DEEP: self._settings.llm_model_deep or self._settings.llm_model,
            Tier.RENDER: self._settings.llm_model_render or self._settings.llm_model,
        }

        match self._settings.llm_provider:
            case ProviderType.ANTHROPIC:
                return AnthropicProvider(
                    api_key=self._settings.anthropic_api_key.get_secret_value()
                    if self._settings.anthropic_api_key
                    else "",
                    tier_map=tier_map,
                )
            case ProviderType.OPENROUTER:
                return OpenRouterProvider(
                    api_key=self._settings.openrouter_api_key.get_secret_value()
                    if self._settings.openrouter_api_key
                    else "",
                    tier_map=tier_map,
                )
            case ProviderType.OLLAMA:
                raise NotImplementedError(
                    "Ollama provider is not implemented in v1. "
                    "Use llm_provider=anthropic; Ollama support is planned for v1.1."
                )
            case ProviderType.BEDROCK:
                raise NotImplementedError(
                    "Bedrock provider is not implemented in v1. "
                    "Use llm_provider=anthropic; Bedrock support is planned for v1.1."
                )
            case _:
                raise ValueError(
                    f"Unknown llm_provider: {self._settings.llm_provider!r}. "
                    f"Must be one of: {[p.value for p in ProviderType]}."
                )
