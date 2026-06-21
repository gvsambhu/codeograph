"""Mock LLM Provider for testing (ADR-018 Fork 3).

Import failure-injection error types directly from ``anthropic`` in your tests:

    from anthropic import RateLimitError, APIConnectionError, APITimeoutError, APIStatusError
    mock = MockLlmProviderBuilder().with_failure(0, RateLimitError(...)).build()
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider

T = TypeVar("T", bound=BaseModel)


class MockLlmProviderError(Exception):
    """Base error for MockLlmProvider failures."""

    pass


@dataclass
class CallContext:
    tier: Tier
    messages: list[Message]
    schema: type[BaseModel]
    override_model: str | None
    max_tokens: int


@dataclass
class MockLlmProvider(LlmProvider):
    responses: list[Any] = field(default_factory=list)
    responses_by_prompt_hash: dict[str, Any] = field(default_factory=dict)
    failures: dict[int, Exception] = field(default_factory=dict)
    model_version: str = "mock-model-1.0"
    calls: list[CallContext] = field(default_factory=list)

    def count_tokens(self, messages: list[Message]) -> int:
        return sum(len(str(m.content)) for m in messages) // 4  # rough estimate

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or self.model_version

    def _compute_hash(self, messages: list[Message]) -> str:
        # Simple hash of messages for responses_by_prompt_hash lookup
        msg_str = json.dumps([{"role": m.role, "content": m.content} for m in messages], sort_keys=True)
        return hashlib.sha256(msg_str.encode("utf-8")).hexdigest()

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        call_index = len(self.calls)
        self.calls.append(
            CallContext(
                tier=tier,
                messages=messages,
                schema=schema,
                override_model=override_model,
                max_tokens=max_tokens,
            )
        )

        if call_index in self.failures:
            raise self.failures[call_index]

        prompt_hash = self._compute_hash(messages)
        if prompt_hash in self.responses_by_prompt_hash:
            parsed = self.responses_by_prompt_hash[prompt_hash]
        elif self.responses:
            parsed = self.responses.pop(0)
        else:
            raise MockLlmProviderError(f"No mock response configured for call index {call_index}")

        # If it's a dict, instantiate the schema
        if isinstance(parsed, dict):
            parsed = schema(**parsed)

        return LlmResult(
            value=parsed,
            model=self.resolve_model(tier, override_model),
            usage=TokenUsage(input_tokens=10, output_tokens=10, cached_tokens=0),
            latency_ms=100,
        )


class MockLlmProviderBuilder:
    def __init__(self) -> None:
        self._responses: list[Any] = []
        self._responses_by_hash: dict[str, Any] = {}
        self._failures: dict[int, Exception] = {}
        self._model_version = "mock-model-1.0"

    def with_response(self, response: Any) -> "MockLlmProviderBuilder":
        self._responses.append(response)
        return self

    def with_responses_by_hash(self, responses: dict[str, Any]) -> "MockLlmProviderBuilder":
        self._responses_by_hash.update(responses)
        return self

    def with_failure(self, call_index: int, error: Exception) -> "MockLlmProviderBuilder":
        self._failures[call_index] = error
        return self

    def with_model_version(self, model_version: str) -> "MockLlmProviderBuilder":
        self._model_version = model_version
        return self

    def build(self) -> MockLlmProvider:
        return MockLlmProvider(
            responses=self._responses.copy(),
            responses_by_prompt_hash=self._responses_by_hash.copy(),
            failures=self._failures.copy(),
            model_version=self._model_version,
            calls=[],
        )
