"""Unit tests for Settings validators and YamlConfigSource instance methods."""

from __future__ import annotations

import pytest


def test_settings_defaults_instantiate():
    """Settings with defaults should work without env vars."""
    from codeograph.config.settings import Settings
    s = Settings()
    assert s.llm_concurrency == 5


def test_settings_llm_concurrency_validator_rejects_zero():
    from pydantic import ValidationError

    from codeograph.config.settings import Settings
    with pytest.raises(ValidationError):
        Settings(llm_concurrency=0)


def test_settings_llm_concurrency_validator_rejects_above_50():
    from pydantic import ValidationError

    from codeograph.config.settings import Settings
    with pytest.raises(ValidationError):
        Settings(llm_concurrency=51)


def test_settings_max_pass1_failure_ratio_validator_rejects_negative():
    from pydantic import ValidationError

    from codeograph.config.settings import Settings
    with pytest.raises(ValidationError):
        Settings(max_pass1_failure_ratio=-0.1)


def test_settings_max_pass1_failure_ratio_validator_rejects_above_1():
    from pydantic import ValidationError

    from codeograph.config.settings import Settings
    with pytest.raises(ValidationError):
        Settings(max_pass1_failure_ratio=1.1)


def test_yaml_source_instance_methods(tmp_path, monkeypatch):
    """Cover get_field_value and __call__ instance methods."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("llm_concurrency: 3\n", encoding="utf-8")

    from importlib import reload

    import codeograph.config.yaml_source as ys_mod
    reload(ys_mod)

    # We need a Settings class to instantiate YamlConfigSource
    # Use a minimal mock settings source
    from pydantic_settings import BaseSettings
    src = ys_mod.YamlConfigSource(BaseSettings)

    # __call__ returns the full dict
    result = src()
    assert result.get("llm_concurrency") == 3

    # get_field_value returns a specific field value
    from pydantic.fields import FieldInfo
    fi = FieldInfo()
    val = src.get_field_value(fi, "llm_concurrency")
    assert val == 3
