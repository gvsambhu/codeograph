"""Unit tests for codeograph/config/yaml_source.py (DC1 coverage gap)."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_yaml_source_returns_empty_when_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """No config.yaml → _load() returns {}."""
    monkeypatch.chdir(tmp_path)
    from codeograph.config.yaml_source import YamlConfigSource
    assert YamlConfigSource._load() == {}


def test_yaml_source_reads_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """config.yaml present → _load() returns its contents."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("llm_provider: anthropic\n", encoding="utf-8")
    from importlib import reload

    import codeograph.config.yaml_source as ys_mod
    reload(ys_mod)  # re-evaluate _CONFIG_YAML relative to new cwd
    data = ys_mod.YamlConfigSource._load()
    assert data.get("llm_provider") == "anthropic"


def test_yaml_source_returns_empty_for_non_dict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """config.yaml contains a list → treated as {} (not a dict)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("- item1\n- item2\n", encoding="utf-8")
    from importlib import reload

    import codeograph.config.yaml_source as ys_mod
    reload(ys_mod)
    assert ys_mod.YamlConfigSource._load() == {}
