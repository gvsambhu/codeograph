import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr, ValidationError

from codeograph.config.settings import Settings
from codeograph.llm.models import ProviderType
from codeograph.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from codeograph.llm.providers.openrouter_provider import OpenRouterProvider
from codeograph.llm.resolver import LlmProviderResolver


def test_settings_openai_compat_validation_success():
    """Verify Settings loads with valid OpenAI-compatible settings (D-001-5)."""
    # Create settings with valid base URL and api key
    settings = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
        openai_compat_api_key=SecretStr("mock-key"),
    )
    assert settings.openai_compat_base_url == "https://api.example.com/v1"
    assert settings.openai_compat_api_key is not None
    assert settings.openai_compat_api_key.get_secret_value() == "mock-key"


def test_settings_openai_compat_validation_fails_when_missing_url():
    """Verify Settings raises ValidationError if base URL is missing when provider is openai_compatible (D-001-5)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            llm_provider=ProviderType.OPENAI_COMPATIBLE,
            openai_compat_base_url=None,
            openai_compat_api_key=SecretStr("mock-key"),
        )
    assert "openai_compat_base_url" in str(exc_info.value)


def test_settings_openai_compat_validation_fails_on_invalid_url():
    """Verify Settings raises ValidationError if base URL doesn't start with http:// or https:// (D-001-5)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            llm_provider=ProviderType.OPENAI_COMPATIBLE,
            openai_compat_base_url="invalid-url",
            openai_compat_api_key=SecretStr("mock-key"),
        )
    assert "openai_compat_base_url" in str(exc_info.value)


def test_settings_no_bare_openai_api_key_read(monkeypatch):
    """Verify that bare OPENAI_API_KEY is not read automatically by Settings (D-001-5)."""
    monkeypatch.setenv("OPENAI_API_KEY", "bare-key")
    settings = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
    )
    assert settings.openai_compat_api_key is None


def test_settings_openai_compat_accepts_arbitrary_model():
    """Verify model setting accepts arbitrary strings (no allowlist restrictions) (D-001-5)."""
    settings = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
        llm_model="custom/some-model-v2",
    )
    assert settings.llm_model == "custom/some-model-v2"


def test_resolver_resolves_openai_compatible():
    """Verify LlmProviderResolver correctly instantiates OpenAICompatibleProvider (D-013-7)."""
    settings = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
        openai_compat_api_key=SecretStr("mock-key"),
        llm_model="some-model",
    )
    resolver = LlmProviderResolver(settings)
    provider = resolver.resolve()
    assert isinstance(provider, OpenAICompatibleProvider)
    chat = provider._chat

    assert isinstance(chat, ChatOpenAI)
    assert chat.openai_api_base == settings.openai_compat_base_url
    assert chat.model_name == settings.llm_model
    assert isinstance(chat.openai_api_key, SecretStr)
    assert settings.openai_compat_api_key is not None
    assert chat.openai_api_key.get_secret_value() == settings.openai_compat_api_key.get_secret_value()


def test_openrouter_provider_preset():
    """Verify OpenRouterProvider resolves as a preset subclass with correct base URL (D-013-7)."""
    settings = Settings(
        llm_provider=ProviderType.OPENROUTER,
        openrouter_api_key=SecretStr("mock-key"),
        llm_model="some-model",
    )
    resolver = LlmProviderResolver(settings)
    provider = resolver.resolve()
    assert isinstance(provider, OpenRouterProvider)
    chat = provider._chat
    assert isinstance(chat, ChatOpenAI)
    assert chat.openai_api_base == "https://openrouter.ai/api/v1"


def test_settings_resolved_provider_label():
    """Verify that settings.resolved_provider_label implements hybrid resolution (D-001-5 / D-013-7)."""
    # Case 1: Explicit label is set for OpenAI compatible provider
    settings_explicit = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
        openai_compat_provider_label="my-custom-provider",
    )
    assert settings_explicit.resolved_provider_label == "my-custom-provider"

    # Case 2: Unset label falls back to normalized host (with port, path, subdomains)
    settings_fallback = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="http://Sub.HostName.Com:8080/v1/endpoints/",
    )
    assert settings_fallback.resolved_provider_label == "sub.hostname.com"

    # Case 3: Falls back to "openai_compatible" if base URL is somehow not validated/configured
    settings_anthropic = Settings(
        llm_provider=ProviderType.ANTHROPIC,
        anthropic_api_key=SecretStr("mock-key"),
    )
    assert settings_anthropic.resolved_provider_label == "anthropic"

    settings_openrouter = Settings(
        llm_provider=ProviderType.OPENROUTER,
        openrouter_api_key=SecretStr("mock-key"),
    )
    assert settings_openrouter.resolved_provider_label == "openrouter"
