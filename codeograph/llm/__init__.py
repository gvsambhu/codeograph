from codeograph.llm.errors import (
    LlmAuthError,
    LlmBadInputError,
    LlmContentPolicyError,
    LlmError,
    LlmRateLimitExhausted,
    LlmSchemaValidationError,
    LlmTransientError,
)
from codeograph.llm.factory import build_default_stack
from codeograph.llm.provider import LlmProvider
from codeograph.llm.models import CacheHint, CallContext, LlmResult, Message, Purpose, Tier, TokenUsage

try:
    from codeograph.llm._prompts_generated import PromptId
except ImportError:
    # Fallback stub when scripts/gen_prompt_constants.py hasn't been run yet
    # (e.g. fresh checkout before pre-commit installation).
    class PromptId:  # type: ignore[no-redef]
        pass


__all__ = [
    "Tier",
    "Purpose",
    "CallContext",
    "CacheHint",
    "Message",
    "LlmResult",
    "TokenUsage",
    "LlmError",
    "LlmTransientError",
    "LlmBadInputError",
    "LlmAuthError",
    "LlmContentPolicyError",
    "LlmSchemaValidationError",
    "LlmRateLimitExhausted",
    "LlmProvider",
    "build_default_stack",
    "PromptId",
]
