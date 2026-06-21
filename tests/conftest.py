"""
Test-suite pytest configuration (tests/conftest.py).

Registers:
  --update-goldens  CLI flag (consumed by tests/integration/test_goldens.py)
  update_goldens    fixture that exposes the flag value to test functions
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from codeograph.llm.errors import LlmError
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Overwrite stored golden graph files instead of comparing against them.",
    )


@pytest.fixture
def update_goldens(request: pytest.FixtureRequest) -> bool:
    """True when --update-goldens was passed on the command line."""
    return bool(request.config.getoption("--update-goldens"))


# --- LLM Test Fixtures (DC2) ---


class MockLlmProvider(LlmProvider):
    """A mock LLM provider for unit tests that avoids live API calls."""

    mock_response: LlmResult[BaseModel] | None = None

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or "mock-model"

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[BaseModel]:
        self.calls.append(
            {
                "tier": tier,
                "messages": messages,
                "schema": schema,
                "override_model": override_model,
                "max_tokens": max_tokens,
            }
        )
        if self.mock_response is not None:
            return self.mock_response
        # Dummy instantiation — might fail if schema has required fields without defaults
        try:
            val = schema()
        except Exception:
            val = None  # Placeholder; learner should handle proper mocking

        return LlmResult(
            value=val,
            usage=TokenUsage(input_tokens=10, output_tokens=10, cached_tokens=0),
            model="mock-model",
            latency_ms=100,
        )

    def complete_structured_many(
        self,
        tier: Tier,
        requests: list[tuple[list[Message], type[BaseModel]]],
        *,
        max_concurrent: int = 5,
        override_model: str | None = None,
    ) -> list[LlmResult[BaseModel] | LlmError]:
        results = []
        for msgs, schema in requests:
            try:
                results.append(self.complete_structured(tier, msgs, schema, override_model=override_model))
            except LlmError as e:
                results.append(e)
        return results

    def count_tokens(self, text: str) -> int:
        return len(text) // 4


@pytest.fixture
def mock_llm_provider() -> MockLlmProvider:
    return MockLlmProvider()


@pytest.fixture
def make_mock_provider():
    from tests.fixtures.llm.mock_provider import MockLlmProviderBuilder

    return MockLlmProviderBuilder


@pytest.fixture
def tmp_cache_db(tmp_path: Path):
    from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend

    db_file = tmp_path / "cache" / "test_cache.db"
    backend = SQLiteCacheBackend(db_file)
    yield backend
    # teardown if needed


@pytest.fixture
def tmp_telemetry_jsonl(tmp_path: Path):
    from codeograph.telemetry.jsonl_emitter import JsonlEmitter

    log_file = tmp_path / "telemetry" / "test_telemetry.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    emitter = JsonlEmitter(log_file)
    yield emitter
    emitter.close()


@pytest.fixture
def mock_prompt_loader(tmp_path: Path):
    from codeograph.llm.prompts.loader import PromptLoader

    prompts_dir = tmp_path / "prompts"

    # Create the Pass 1 mock prompt
    p1_dir = prompts_dir / "annotate_node"
    p1_dir.mkdir(parents=True, exist_ok=True)
    (p1_dir / "v1.md").write_text("---\ncontent_hash_pin: 1359ce8f\n---\nSystem prompt here.", encoding="utf-8")
    (p1_dir / "default.yaml").write_text("default: v1\n", encoding="utf-8")

    # Create the Pass 2 mock prompt
    p2_dir = prompts_dir / "synthesize_corpus"
    p2_dir.mkdir(parents=True, exist_ok=True)
    (p2_dir / "v1.md").write_text("---\ncontent_hash_pin: 1359ce8f\n---\nSystem prompt here.", encoding="utf-8")
    (p2_dir / "default.yaml").write_text("default: v1\n", encoding="utf-8")

    return PromptLoader(prompts_dir)


@pytest.fixture
def runner():
    from click.testing import CliRunner

    return CliRunner()
