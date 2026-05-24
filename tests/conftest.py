"""
Test-suite pytest configuration (tests/conftest.py).

Registers:
  --update-goldens  CLI flag (consumed by tests/test_golden.py)
  update_goldens    fixture that exposes the flag value to test functions
"""

from __future__ import annotations

import pytest


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

from codeograph.llm.provider import LlmProvider
from codeograph.llm.types import Message, Tier, LlmResult, TokenUsage
from pydantic import BaseModel
import shutil

class MockLlmProvider(LlmProvider):
    """A mock LLM provider for unit tests that avoids live API calls."""
    
    def __init__(self):
        self.calls: list[dict] = []
        # TODO(learner): allow tests to configure predefined responses or errors here
        
    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[BaseModel]:
        # TODO(learner): return a mock response that matches `schema`
        self.calls.append({
            "tier": tier,
            "messages": messages,
            "schema": schema,
            "override_model": override_model,
            "max_tokens": max_tokens,
        })
        if getattr(self, "mock_response", None) is not None:
            return self.mock_response
        # Dummy instantiation — might fail if schema has required fields without defaults
        try:
            val = schema()
        except Exception:
            val = None # Placeholder; learner should handle proper mocking
            
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
        max_concurrent: int = 5,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> list[LlmResult[BaseModel]]:
        # Default fallback to sequential for easy mocking
        return [
            self.complete_structured(tier, msgs, schema, max_tokens, temperature)
            for msgs, schema in requests
        ]
        
    def count_tokens(self, text: str) -> int:
        return len(text) // 4


@pytest.fixture
def mock_llm_provider() -> MockLlmProvider:
    return MockLlmProvider()

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
    prompts_dir.mkdir()
    # TODO(learner): Create mock prompt files in prompts_dir here
    return PromptLoader(prompts_dir)
