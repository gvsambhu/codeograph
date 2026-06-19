from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeVar

T = TypeVar("T")


class ProviderType(StrEnum):
    """The supported LLM backend providers."""

    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"


class Tier(StrEnum):
    """Tier resolves to a concrete model via a tier_map."""

    FAST = "fast"  # Pass 1 — annotation, high throughput, cheap model
    DEEP = "deep"  # Pass 2 — synthesis, larger model
    RENDER = "render"  # Pass 3 — conversion output, top-tier model


class Purpose(StrEnum):
    """The pass-specific purpose of an LLM call."""

    ANNOTATE = "annotate"  # Pass 1
    SYNTHESIZE = "synthesize"  # Pass 2
    RENDER = "render"  # Pass 3


@dataclass(frozen=True)
class CallContext:
    """Pass-specific metadata carried into cache/telemetry wrappers."""

    purpose: Purpose
    prompt_id: str
    prompt_version: str
    prompt_content_hash: str
    corpus_id: str
    provider_name: str = "unknown"  # e.g. "anthropic", "ollama" — populates telemetry + cache provider field


@dataclass(frozen=True)
class CacheHint:
    """Abstracts per-provider cache mechanics (e.g. Anthropic ephemeral cache)."""

    ttl: Literal["5m", "1h"] = "5m"


@dataclass(frozen=True)
class Message:
    """A standard chat message with an optional cache hint."""

    role: Literal["system", "user", "assistant"]
    content: str
    cache: CacheHint | None = None


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting supporting both exact billing and pre-flight estimates."""

    input_tokens: int  # provider response.usage (exact, billing source)
    output_tokens: int  # provider response.usage
    cached_tokens: int  # Anthropic prompt-cache hits (0 if N/A)
    input_estimated: int | None = None  # populated only if count_tokens was called


@dataclass(frozen=True)
class LlmResult[T]:
    """The standard result from a complete_structured call."""

    value: T
    usage: TokenUsage
    model: str
    latency_ms: int
    cache_hit: bool = False  # True when returned from CachingLlmProvider without a live call
