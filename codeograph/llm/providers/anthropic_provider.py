from langchain_anthropic import ChatAnthropic
from codeograph.llm.types import Tier
from codeograph.llm.providers.langchain_base import LangChainLlmProvider

class AnthropicProvider(LangChainLlmProvider):
    def __init__(self, api_key: str, tier_map: dict[Tier, str], **kwargs):
        if not api_key:
            raise ValueError("Anthropic API key cannot be empty.")
        if not tier_map:
            raise ValueError("tier_map must map Tiers to model strings.")
        for tier in Tier:
            if tier not in tier_map:
                raise ValueError(f"Missing model mapping for tier: {tier}")
                
        chat = ChatAnthropic(api_key=api_key, **kwargs)
        super().__init__(chat, tier_map)
