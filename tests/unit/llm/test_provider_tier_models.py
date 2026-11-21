"""Every LLM call runs on the model its tier (or an explicit override) resolves to.

Uses the real LangChain chat classes. The structured-output entry point is replaced on the class
with a spy that records the model of the chat object that is actually invoked, so no network is
touched and the provider class itself is not patched.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from codeograph.config.settings import Settings
from codeograph.llm.models import Message, ProviderType, Tier
from codeograph.llm.provider import LlmProvider
from codeograph.llm.providers.anthropic_provider import AnthropicProvider
from codeograph.llm.providers.langchain_base import LangChainLlmProvider
from codeograph.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from codeograph.llm.providers.openrouter_provider import OpenRouterProvider
from codeograph.llm.resolver import LlmProviderResolver

TIER_MAP = {Tier.FAST: "model-fast", Tier.DEEP: "model-deep", Tier.RENDER: "model-render"}


class _Out(BaseModel):
    text: str


def _model_of(chat: BaseChatModel) -> str:
    if isinstance(chat, ChatAnthropic):
        return chat.model
    assert isinstance(chat, ChatOpenAI)
    return chat.model_name


def _anthropic() -> LangChainLlmProvider:
    return AnthropicProvider(api_key="k", tier_map=TIER_MAP)


def _openai_compatible() -> LangChainLlmProvider:
    return OpenAICompatibleProvider(api_key="k", base_url="https://api.example.com/v1", tier_map=TIER_MAP)


def _openrouter() -> LangChainLlmProvider:
    return OpenRouterProvider(api_key="k", tier_map=TIER_MAP)


FACTORIES = [_anthropic, _openai_compatible, _openrouter]


@pytest.fixture
def invoked_models(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the model of each chat object whose structured chain is invoked."""
    seen: list[str] = []

    def spy(self: BaseChatModel, schema: Any, **_: Any) -> RunnableLambda[Any, dict[str, Any]]:
        def invoke(_msgs: Any) -> dict[str, Any]:
            seen.append(_model_of(self))
            return {"parsed": _Out(text="ok"), "raw": AIMessage(content="")}

        return RunnableLambda(invoke)

    for cls in (ChatAnthropic, ChatOpenAI):
        monkeypatch.setattr(cls, "with_structured_output", spy)
    return seen


@pytest.mark.parametrize("make", FACTORIES)
@pytest.mark.parametrize("tier", list(Tier))
def test_call_runs_on_the_tier_model(make: Any, tier: Tier, invoked_models: list[str]) -> None:
    provider = make()

    result = provider.complete_structured(tier, [Message(role="user", content="hi")], _Out)

    assert invoked_models == [TIER_MAP[tier]]
    assert result.model == TIER_MAP[tier]


@pytest.mark.parametrize("make", FACTORIES)
def test_override_model_wins_over_the_tier(make: Any, invoked_models: list[str]) -> None:
    provider = make()

    result = provider.complete_structured(
        Tier.FAST, [Message(role="user", content="hi")], _Out, override_model="model-override"
    )

    assert invoked_models == ["model-override"]
    assert result.model == "model-override"
    assert provider.resolve_model(Tier.FAST, "model-override") == "model-override"


def test_anthropic_provider_builds_a_real_chat_model_per_tier() -> None:
    provider = _anthropic()

    for tier, model in TIER_MAP.items():
        chat = provider._chat_for(provider.resolve_model(tier))
        assert isinstance(chat, ChatAnthropic)
        assert chat.model == model


def test_chat_object_is_built_once_per_model() -> None:
    provider = _anthropic()

    assert provider._chat_for("model-fast") is provider._chat_for("model-fast")


def _settings(provider: ProviderType) -> Settings:
    return Settings(
        llm_provider=provider,
        anthropic_api_key=SecretStr("k"),
        openrouter_api_key=SecretStr("k"),
        openai_compat_api_key=SecretStr("k"),
        openai_compat_base_url="https://api.example.com/v1",
        llm_model="default-model",
        llm_model_fast="model-fast",
        llm_model_deep="model-deep",
        llm_model_render="model-render",
    )


@pytest.mark.parametrize(
    ("provider_type", "expected_cls"),
    [
        (ProviderType.ANTHROPIC, AnthropicProvider),
        (ProviderType.OPENROUTER, OpenRouterProvider),
        (ProviderType.OPENAI_COMPATIBLE, OpenAICompatibleProvider),
    ],
)
def test_resolver_builds_every_provider_type(provider_type: ProviderType, expected_cls: type[LlmProvider]) -> None:
    provider = LlmProviderResolver(_settings(provider_type)).resolve()

    assert isinstance(provider, expected_cls)
    assert provider.resolve_model(Tier.FAST) == "model-fast"
    assert provider.resolve_model(Tier.RENDER) == "model-render"


@pytest.fixture
def output_caps(monkeypatch: pytest.MonkeyPatch) -> list[int | None]:
    """Record the output cap in the request each chat object would send for a call."""
    seen: list[int | None] = []

    def spy(self: BaseChatModel, schema: Any, **_: Any) -> RunnableLambda[Any, dict[str, Any]]:
        def invoke(_msgs: Any) -> dict[str, Any]:
            payload = self._get_request_payload([])  # type: ignore[attr-defined]
            seen.append(payload.get("max_tokens", payload.get("max_completion_tokens")))
            return {"parsed": _Out(text="ok"), "raw": AIMessage(content="")}

        return RunnableLambda(invoke)

    for cls in (ChatAnthropic, ChatOpenAI):
        monkeypatch.setattr(cls, "with_structured_output", spy)
    return seen


@pytest.mark.parametrize("make", FACTORIES)
def test_the_calls_output_cap_reaches_the_chat_model(make: Any, output_caps: list[int | None]) -> None:
    provider = make()

    provider.complete_structured(Tier.FAST, [Message(role="user", content="hi")], _Out, max_tokens=321)
    provider.complete_structured(Tier.FAST, [Message(role="user", content="hi")], _Out, max_tokens=77)

    assert output_caps == [321, 77]


def test_one_calls_cap_does_not_change_the_shared_chat_object(output_caps: list[int | None]) -> None:
    provider = _anthropic()
    shared = provider._chat_for("model-fast")
    assert isinstance(shared, ChatAnthropic)
    before = shared.max_tokens

    provider.complete_structured(Tier.FAST, [Message(role="user", content="hi")], _Out, max_tokens=5)

    assert output_caps == [5]
    assert provider._chat_for("model-fast") is shared
    assert shared.max_tokens == before
