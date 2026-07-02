import time
from typing import Any, TypeVar

import anthropic
import pydantic
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from codeograph.llm.errors import (
    LlmAuthError,
    LlmBadInputError,
    LlmContentPolicyError,
    LlmError,
    LlmSchemaValidationError,
    LlmTransientError,
)
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


def _classify_error(e: Exception) -> LlmError:
    """Classify raw LangChain/SDK exception into LlmError taxonomy."""
    if isinstance(e, (pydantic.ValidationError, OutputParserException)):
        return LlmSchemaValidationError(
            f"Failed to parse LLM output into the requested schema: {str(e)}. "
            "If using a non-default OpenAI-compatible endpoint, verify it supports "
            "structured output / tool-calling (ADR-013 D-013-7)."
        )

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

    def __init__(self, chat_model: BaseChatModel, tier_map: dict[Tier, str]):
        self._chat = chat_model
        self._tier_map = tier_map

    def _to_langchain_messages(self, messages: list[Message]) -> list[BaseMessage]:
        lc_msgs: list[BaseMessage] = []
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

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or self._tier_map[tier]

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
            # `out` is dict[str, Any] when include_raw=True; mypy can't narrow the union return,
            # so we cast via Any to access the keys.
            out_dict: dict[str, Any] = out  # type: ignore[assignment]
            res = out_dict["parsed"]
            raw_msg = out_dict["raw"]

            usage_meta = getattr(raw_msg, "usage_metadata", None)
            if usage_meta:
                usage = TokenUsage(
                    input_tokens=usage_meta.get("input_tokens", 0),
                    output_tokens=usage_meta.get("output_tokens", 0),
                    cached_tokens=(usage_meta.get("input_token_details", {}).get("cache_read", 0)),
                )
            else:
                usage = TokenUsage(input_tokens=0, output_tokens=0, cached_tokens=0)
        except Exception as e:
            raise _classify_error(e) from e

        latency = int((time.monotonic() - start) * 1000)

        return LlmResult(value=res, usage=usage, model=model_name, latency_ms=latency)
