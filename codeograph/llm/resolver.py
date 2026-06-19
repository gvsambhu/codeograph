"""
LlmProviderResolver — resolves and instantiates the configured LLM provider subclass.
"""

from __future__ import annotations

from codeograph.config.settings import Settings
from codeograph.llm.provider import LlmProvider


class LlmProviderResolver:
    """Resolves and instantiates the configured LLM provider subclass."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self) -> LlmProvider:
        # TODO: The learner should port the match-case logic selecting the LLM provider here.
        # Reference: Look at the previous matching blocks in main.py / llm_corpus_enricher.py.
        # Needs to support: AnthropicProvider, and raise NotImplementedError for Ollama/Bedrock.
        raise NotImplementedError("LlmProviderResolver.resolve needs to be implemented by the learner.")
