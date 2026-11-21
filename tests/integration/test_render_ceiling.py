"""``codeograph render`` stops at a spend ceiling: files already written are kept, the exit status is 1."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import pytest
from click.testing import CliRunner
from pydantic import BaseModel

from codeograph.cli.main import cli
from codeograph.llm.errors import LlmCeilingExceededError
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider
from codeograph.renderers.typescript_nestjs.models import RenderedSource

# Pass 0 parses Java through the JVM sidecar, so this belongs with the Java-enabled integration job.
pytestmark = pytest.mark.slow

T = TypeVar("T", bound=BaseModel)


class _CeilingOnCallProvider(LlmProvider):
    """Renders every class successfully until call number ``ceiling_on``, which raises the ceiling error."""

    def __init__(self, ceiling_on: int | None) -> None:
        self.ceiling_on = ceiling_on
        self.calls = 0

    def count_tokens(self, messages: list[Message]) -> int:
        return 1

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return "m"

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:
        self.calls += 1
        if self.ceiling_on is not None and self.calls >= self.ceiling_on:
            raise LlmCeilingExceededError("LLM call ceiling of 2 calls reached (calls made: 2)")
        value = RenderedSource(content=f"// call {self.calls}\nexport class C{self.calls} {{}}\n")
        return LlmResult(
            value=schema.model_validate(value.model_dump()),
            usage=TokenUsage(input_tokens=1, output_tokens=1, cached_tokens=0),
            model="m",
            latency_ms=1,
        )


def _run_output(tmp_path: Path) -> Path:
    """An output directory holding the graph of a small corpus and no annotations (render needs both files)."""
    run_dir = tmp_path / "run-output"
    result = CliRunner().invoke(
        cli, ["run", "tests/fixtures/corpora/minimal_rest", "--out", str(run_dir), "--ast-only"]
    )
    assert result.exit_code == 0, result.output
    (run_dir / "llm-annotations.json").write_text("[]", encoding="utf-8")
    return run_dir


def _render(tmp_path: Path, run_dir: Path, provider: _CeilingOnCallProvider):
    from unittest.mock import patch

    with patch("codeograph.llm.resolver.LlmProviderResolver.resolve", return_value=provider):
        return CliRunner().invoke(
            cli,
            [
                "render",
                "--from",
                str(run_dir),
                "--out",
                str(tmp_path / "ts-out"),
                "--max-classes-per-domain",
                "0",
                "--no-scaffold",
            ],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache"), "CODEOGRAPH_LLM_CONCURRENCY": "1"},
        )


def test_render_stops_at_a_ceiling_keeps_its_files_and_exits_1(tmp_path: Path) -> None:
    run_dir = _run_output(tmp_path)
    complete = _CeilingOnCallProvider(ceiling_on=None)
    assert _render(tmp_path / "full", run_dir, complete).exit_code == 0
    selected = complete.calls
    assert selected > 3, "the fixture must select more classes than the ceiling allows"

    provider = _CeilingOnCallProvider(ceiling_on=3)
    result = _render(tmp_path, run_dir, provider)

    assert result.exit_code == 1, result.output
    assert "ceiling of 2 calls" in result.output
    assert f"rendered 2 of {selected} classes" in result.output
    assert provider.calls == 3, "no class is started after the one that hit the ceiling"
    assert "Done. Wrote" not in result.output
    written = [p for p in (tmp_path / "ts-out").rglob("*.ts") if not p.name.endswith(".module.ts")]
    assert len(written) == 2


def test_other_per_class_failures_still_skip_only_that_class(tmp_path: Path) -> None:
    from codeograph.llm.errors import LlmBadInputError

    class _OneBadClassProvider(_CeilingOnCallProvider):
        def complete_structured(self, *args, **kwargs):
            if self.calls == 1:
                self.calls += 1
                raise LlmBadInputError("bad class")
            return super().complete_structured(*args, **kwargs)

    run_dir = _run_output(tmp_path)

    full_dir = tmp_path / "full"
    full_result = _render(full_dir, run_dir, _CeilingOnCallProvider(ceiling_on=None))
    assert full_result.exit_code == 0, full_result.output
    full_root = full_dir / "ts-out"
    full_files = {
        path.relative_to(full_root): path.read_text(encoding="utf-8")
        for path in full_root.rglob("*.ts")
        if not path.name.endswith(".module.ts")
    }
    failing_files = {path for path, content in full_files.items() if "// call 2\n" in content}
    assert len(failing_files) == 1

    result = _render(tmp_path, run_dir, _OneBadClassProvider(ceiling_on=None))

    assert result.exit_code == 0, result.output
    output_root = tmp_path / "ts-out"
    actual_files = {
        path.relative_to(output_root): path.read_text(encoding="utf-8")
        for path in output_root.rglob("*.ts")
        if not path.name.endswith(".module.ts")
    }
    expected_files = {path: content for path, content in full_files.items() if path not in failing_files}
    assert actual_files == expected_files, "only the failing class is absent; every later class is rendered"
