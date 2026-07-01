class LlmError(Exception):
    """Base class for all LLM-related exceptions."""

    pass


class LlmTransientError(LlmError):
    """Network, 429, 5xx — retry candidate."""

    pass


class LlmBadInputError(LlmError):
    """400 — surface to caller."""

    pass


class LlmAuthError(LlmError):
    """401/403 — surface to caller."""

    pass


class LlmContentPolicyError(LlmError):
    """Policy violation — surface to caller."""

    pass


class LlmSchemaValidationError(LlmError):
    """Response didn't parse into requested schema — surface to caller."""

    pass


class LlmRateLimitExhausted(LlmTransientError):
    """Rate limit exhausted after wrapper's retries."""

    pass


class LlmCeilingExceededError(LlmError):
    """Ceiling limit (calls or tokens) exceeded during run."""

    pass
