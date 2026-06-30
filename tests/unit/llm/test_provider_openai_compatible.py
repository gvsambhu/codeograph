# ruff: noqa: F401, F841, E501
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from codeograph.config.settings import Settings
from codeograph.llm.models import ProviderType, Tier
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
    # TODO(learner): Assert that setting values are correctly assigned and no validation error is raised


def test_settings_openai_compat_validation_fails_when_missing_url():
    """Verify Settings raises ValidationError if base URL is missing when provider is openai_compatible (D-001-5)."""
    # TODO(learner): Assert that ValidationError is raised when constructing Settings with llm_provider=ProviderType.OPENAI_COMPATIBLE and openai_compat_base_url=None


def test_settings_openai_compat_validation_fails_on_invalid_url():
    """Verify Settings raises ValidationError if base URL doesn't start with http:// or https:// (D-001-5)."""
    # TODO(learner): Assert that ValidationError is raised when openai_compat_base_url is not a valid URL starting with http:// or https://


def test_settings_no_bare_openai_api_key_read(monkeypatch):
    """Verify that bare OPENAI_API_KEY is not read automatically by Settings (D-001-5)."""
    monkeypatch.setenv("OPENAI_API_KEY", "bare-key")
    # TODO(learner): Assert that Settings().openai_compat_api_key is None unless explicitly set via CODEOGRAPH_OPENAI_COMPAT_API_KEY


def test_settings_openai_compat_accepts_arbitrary_model():
    """Verify model setting accepts arbitrary strings (no allowlist restrictions) (D-001-5)."""
    settings = Settings(
        llm_provider=ProviderType.OPENAI_COMPATIBLE,
        openai_compat_base_url="https://api.example.com/v1",
        llm_model="custom/some-model-v2",
    )
    # TODO(learner): Assert that settings.llm_model == "custom/some-model-v2"


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
    # TODO(learner): Assert that the returned provider is an instance of OpenAICompatibleProvider
    # and wraps a ChatOpenAI model with the correct base_url and settings.


def test_openrouter_provider_preset():
    """Verify OpenRouterProvider resolves as a preset subclass with correct base URL (D-013-7)."""
    # TODO(learner): Assert that OpenRouterProvider can be instantiated with an api_key and tier_map,
    # and has the hardcoded OpenRouter base URL.
