from pydantic import BaseModel

from codeograph.llm.errors import LlmError
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider


class DummySchema(BaseModel):
    text: str


class MockProviderBase(LlmProvider):
    def __init__(self):
        self.count = 0
        self.calls = []

    def count_tokens(self, messages: list[Message]) -> int:
        return len(messages)

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or "mock-model"

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[DummySchema],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[DummySchema]:
        self.calls.append(messages)
        self.count += 1
        if self.count == 2:
            raise LlmError("Mock failure")
        return LlmResult(
            value=schema(text=f"success {self.count}"),
            usage=TokenUsage(1, 2, 0, None),
            model="mock-model",
            latency_ms=10,
        )


def test_provider_base_fan_out_failure():
    provider = MockProviderBase()
    requests = [
        ([Message(role="user", content="req1")], DummySchema),
        ([Message(role="user", content="req2")], DummySchema),
        ([Message(role="user", content="req3")], DummySchema),
    ]
    results = provider.complete_structured_many(Tier.FAST, requests)

    assert len(results) == 3
    # Check that success, failure, and success are present.
    # ThreadPoolExecutor might not preserve order if mock is too fast, but we can just check types
    successes = [r for r in results if isinstance(r, LlmResult)]
    failures = [r for r in results if isinstance(r, LlmError)]
    assert len(successes) == 2
    assert len(failures) == 1
    assert "Mock failure" in str(failures[0])


def test_provider_base_default_concurrency():
    from unittest.mock import patch
    provider = MockProviderBase()
    
    with patch("codeograph.llm.provider.ThreadPoolExecutor") as tpe_mock:
        requests = [([Message(role="user", content="req1")], DummySchema)]
        provider.complete_structured_many(Tier.FAST, requests)
        tpe_mock.assert_called_once_with(max_workers=5)
