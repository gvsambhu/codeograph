from codeograph.llm.cache.base import CacheBackend
from codeograph.llm.middleware.caching_llm_provider import CachingLlmProvider
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.middleware.retrying_llm_provider import RetryingLlmProvider
from codeograph.llm.middleware.telemetry_llm_provider import TelemetryLlmProvider
from codeograph.llm.provider import LlmProvider
from codeograph.llm.models import CallContext
from codeograph.telemetry.base import TelemetryEmitter

# Note: Do not use `build_default_stack` in unit tests (where you want a mock provider without
# SQLite/telemetry overhead) or in quick one-off scripts. Instead, instantiate the raw Provider directly.


def build_default_stack(
    provider: LlmProvider, retry_policy: RetryPolicy, cache: CacheBackend, emitter: TelemetryEmitter, ctx: CallContext
) -> LlmProvider:
    """
    Build the standard LLM stack per ADR-013:
    Telemetry -> Caching -> Retry -> Provider
    """
    # Composition order (outer → inner): Telemetry → Caching → Retry → Provider (ADR-013 Fork 3).
    # The local variable is widened to LlmProvider so mypy accepts the progressive wrapping.
    stack: LlmProvider = RetryingLlmProvider(provider, retry_policy)
    stack = CachingLlmProvider(stack, cache, ctx)
    stack = TelemetryLlmProvider(stack, emitter, ctx)
    return stack
