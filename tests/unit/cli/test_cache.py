"""Tests for the ``cache`` command group.

The cache directory is pointed at ``tmp_path`` through the ``CODEOGRAPH_CACHE_DIR``
setting, so the commands run unmodified against a throwaway database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from codeograph.cli.cache import cache_cli
from codeograph.llm.cache.cache_entry import CacheEntry
from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend

ENTRY_COUNT = 3


def _entry(key: str) -> CacheEntry:
    return CacheEntry(
        cache_key=key,
        provider="anthropic",
        model="test-model",
        tier="fast",
        purpose="annotate",
        prompt_id="test_prompt",
        prompt_version="v1",
        prompt_content_hash="hash",
        input_hash="input-hash",
        schema_hash="schema-hash",
        max_tokens=4096,
        input_body="input",
        output_body='{"text": "output"}',
        token_usage_json='{"input_tokens": 10, "output_tokens": 10}',
        created_at="2026-01-01 00:00:00",
    )


@pytest.fixture
def populated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLiteCacheBackend:
    """A cache.db holding ``ENTRY_COUNT`` entries, found by the CLI through settings."""
    monkeypatch.setenv("CODEOGRAPH_CACHE_DIR", str(tmp_path))
    backend = SQLiteCacheBackend(tmp_path / "cache.db")
    for i in range(ENTRY_COUNT):
        backend.put(f"key-{i}", _entry(f"key-{i}"))
    return backend


def test_cache_cli_stats(populated_cache: SQLiteCacheBackend) -> None:
    result = CliRunner().invoke(cache_cli, ["stats"])

    assert result.exit_code == 0, result.output
    assert f"Total entries: {ENTRY_COUNT}" in result.output


def test_cache_cli_stats_without_a_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEOGRAPH_CACHE_DIR", str(tmp_path))

    result = CliRunner().invoke(cache_cli, ["stats"])

    assert result.exit_code == 0, result.output
    assert "Cache is empty or does not exist." in result.output


def test_cache_cli_purge_all_without_force_deletes_nothing(populated_cache: SQLiteCacheBackend) -> None:
    result = CliRunner().invoke(cache_cli, ["purge", "--all"])

    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output
    assert populated_cache.stats().total_entries == ENTRY_COUNT


def test_cache_cli_purge_all_with_force_deletes_every_entry(populated_cache: SQLiteCacheBackend) -> None:
    result = CliRunner().invoke(cache_cli, ["purge", "--all", "--force"])

    assert result.exit_code == 0, result.output
    assert f"Purged {ENTRY_COUNT} entries." in result.output
    assert populated_cache.stats().total_entries == 0


@pytest.mark.parametrize("args", [["purge"], ["purge", "--force"]])
def test_cache_cli_purge_without_a_criterion_deletes_nothing(
    populated_cache: SQLiteCacheBackend, args: list[str]
) -> None:
    result = CliRunner().invoke(cache_cli, args)

    assert result.exit_code == 0, result.output
    assert "Must specify at least one purge criteria" in result.output
    assert populated_cache.stats().total_entries == ENTRY_COUNT
