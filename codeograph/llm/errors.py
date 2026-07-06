class LlmError(Exception):
    """Base class for all LLM-related exceptions."""

    pass


class LlmTransientError(LlmError):
    """Network, 429, 5xx — retry candidate."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        # Server-supplied Retry-After hint (seconds), if the classifier found one.
        # RetryingLlmProvider prefers this over its own exponential backoff
        # when RetryPolicy.respect_retry_after_header is set (ADR-013 Fork 6).
        self.retry_after_s = retry_after_s


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
