import time
import pydantic
from typing import TypeVar, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.exceptions import OutputParserException
import anthropic

from codeograph.llm.provider import LlmProvider
from codeograph.llm.types import Tier, Message, LlmResult, TokenUsage
from codeograph.llm.errors import (
    LlmError,
    LlmTransientError,
    LlmBadInputError,
    LlmAuthError,
    LlmContentPolicyError,
    LlmSchemaValidationError,
)

T = TypeVar("T")

def _classify_error(e: Exception) -> LlmError:
    """Classify raw LangChain/SDK exception into LlmError taxonomy."""
    if isinstance(e, (pydantic.ValidationError, OutputParserException)):
        return LlmSchemaValidationError(f"Failed to parse LLM output: {str(e)}")

    if isinstance(e, anthropic.APIError):
        if isinstance(e, anthropic.RateLimitError):
            return LlmTransientError("Rate limit exceeded")
        if isinstance(e, (anthropic.InternalServerError, anthropic.APIConnectionError)):
            return LlmTransientError(f"Provider transient error: {str(e)}")
        if isinstance(e, anthropic.BadRequestError):
            return LlmBadInputError(f"Bad request sent to provider: {str(e)}")
        if isinstance(e, anthropic.AuthenticationError):
            return LlmAuthError("Invalid API key or authentication failure")
        if isinstance(e, anthropic.PermissionDeniedError):
            return LlmContentPolicyError("Content policy or permission denied")
            
        status = getattr(e, "status_code", 500)
        if status in (429, 500, 502, 503, 504):
            return LlmTransientError(f"HTTP {status}: {str(e)}")
        if status == 400:
            return LlmBadInputError(f"HTTP {status}: {str(e)}")
        if status in (401, 403):
            return LlmAuthError(f"HTTP {status}: {str(e)}")

    return LlmError(f"Unclassified LLM error: {type(e).__name__} - {str(e)}")

class LangChainLlmProvider(LlmProvider):
    """Base provider wrapping any LangChain BaseChatModel."""

    def __init__(
        self,
        chat_model: BaseChatModel,
        tier_map: dict[Tier, str]
    ):
        self._chat = chat_model
        self._tier_map = tier_map

    def _to_langchain_messages(self, messages: list[Message]) -> list[BaseMessage]:
        lc_msgs = []
        for m in messages:
            kwargs: dict[str, Any] = {}
            if m.cache:
                kwargs["cache_control"] = {"type": "ephemeral", "ttl": m.cache.ttl}
            
            if m.role == "system":
                lc_msgs.append(SystemMessage(content=m.content, additional_kwargs=kwargs))
            elif m.role == "user":
                lc_msgs.append(HumanMessage(content=m.content, additional_kwargs=kwargs))
            elif m.role == "assistant":
                lc_msgs.append(AIMessage(content=m.content, additional_kwargs=kwargs))
        return lc_msgs

    def count_tokens(self, messages: list[Message]) -> int:
        lc_msgs = self._to_langchain_messages(messages)
        try:
            return self._chat.get_num_tokens_from_messages(lc_msgs)
        except Exception as e:
            raise _classify_error(e) from e

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        model_name = override_model or self._tier_map[tier]
        lc_msgs = self._to_langchain_messages(messages)
        
        # We use include_raw=True to get both the parsed Pydantic object AND the raw AIMessage
        # so we can extract token usage metadata.
        chain = self._chat.with_structured_output(schema, include_raw=True)
        
        start = time.monotonic()
        try:
            out = chain.invoke(lc_msgs)
            res = out["parsed"]
            raw_msg = out["raw"]
            
            usage_meta = getattr(raw_msg, "usage_metadata", None)
            if usage_meta:
                usage = TokenUsage(
                    input_tokens=usage_meta.get("input_tokens", 0),
                    output_tokens=usage_meta.get("output_tokens", 0),
                    cached_tokens=(
                        usage_meta.get("input_token_details", {}).get("cache_read", 0)
                    ),
                )
            else:
                usage = TokenUsage(input_tokens=0, output_tokens=0, cached_tokens=0)
        except Exception as e:
            raise _classify_error(e) from e
            
        latency = int((time.monotonic() - start) * 1000)
        
        return LlmResult(
            value=res,
            usage=usage,
            model=model_name,
            latency_ms=latency
        )
