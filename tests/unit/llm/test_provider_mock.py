from pydantic import BaseModel

from codeograph.llm.types import Message, Tier


class DummySchema(BaseModel):
    field: str


def test_mock_provider_basic(mock_llm_provider):
    """Test that the mock provider can be instantiated and returns a basic result."""
    messages = [Message(role="user", content="Hello")]

    # TODO(learner): Provide proper mock configuration before calling
    result = mock_llm_provider.complete_structured(tier=Tier.FAST, messages=messages, schema=DummySchema)

    assert result is not None
    assert result.model == "mock-model"
    # TODO(learner): Assert on result.value once mock is properly configured
