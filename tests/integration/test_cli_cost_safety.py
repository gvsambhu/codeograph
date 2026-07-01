import re
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner
from pydantic import BaseModel

from codeograph.cli.main import cli
from codeograph.llm.models import LlmResult, Message, Tier, TokenUsage
from codeograph.llm.provider import LlmProvider
from tests.fixtures.llm.mock_provider import MockLlmProviderBuilder


class DynamicMockLlmProvider(LlmProvider):
    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return override_model or "mock-model"

    def count_tokens(self, messages: list[Message]) -> int:
        return 100

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[Any]:
        if schema.__name__ == "NodeAnnotation":
            node_id = "unknown"
            user_content = messages[1].content
            match = re.search(r"com\.example\.minimal\.[A-Za-z0-9_]+", user_content)
            if match:
                node_id = match.group(0)
            val = schema(
                node_id=node_id,
                class_name=node_id.split(".")[-1],
                stereotype="Service",
                domain_hint="test",
                description="test",
                methods=[],
            )
        else:
            val = schema(
                description="test",
                architecture_pattern="test",
                domains=[],
                cross_domain_dependencies=[],
            )
        return LlmResult(
            value=val,
            model="mock-model",
            usage=TokenUsage(input_tokens=10, output_tokens=10, cached_tokens=0),
            latency_ms=100,
        )


def _build_mock_provider() -> LlmProvider:
    return DynamicMockLlmProvider()


def test_cli_ast_only_skips_gate(tmp_path):
    """Verify that --ast-only skips pre-flight estimation and gate checks."""
    runner = CliRunner()
    with patch("codeograph.llm.resolver.LlmProviderResolver.resolve") as mock_resolve:
        result = runner.invoke(
            cli,
            [
                "run",
                "tests/fixtures/corpora/minimal_rest",
                "--out",
                str(tmp_path),
                "--ast-only",
            ],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache")},
        )
        assert result.exit_code == 0
        mock_resolve.assert_not_called()
        assert "Pre-flight Cost Estimate" not in result.output


def test_cli_gate_interactive_accept(tmp_path):
    """Verify that gate proceeds on interactive TTY when confirmed."""
    runner = CliRunner()
    mock_provider = _build_mock_provider()

    with (
        patch(
            "codeograph.llm.resolver.LlmProviderResolver.resolve",
            return_value=mock_provider,
        ),
        patch(
            "codeograph.llm.confirmation_gate.ConfirmationGate.is_tty",
            return_value=True,
        ),
        patch("click.confirm", return_value=True) as mock_confirm,
    ):
        result = runner.invoke(
            cli,
            [
                "run",
                "tests/fixtures/corpora/minimal_rest",
                "--out",
                str(tmp_path),
                "--llm-call-confirm-threshold",
                "0",
            ],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache")},
        )
        assert result.exit_code == 0
        mock_confirm.assert_called_once()
        assert "Pre-flight Cost Estimate" in result.output


def test_cli_gate_non_interactive_abort(tmp_path):
    """Verify that gate aborts in non-interactive / non-TTY when threshold exceeded."""
    runner = CliRunner()
    mock_provider = MockLlmProviderBuilder().build()

    with (
        patch(
            "codeograph.llm.resolver.LlmProviderResolver.resolve",
            return_value=mock_provider,
        ),
        patch(
            "codeograph.llm.confirmation_gate.ConfirmationGate.is_tty",
            return_value=False,
        ),
    ):
        result = runner.invoke(
            cli,
            [
                "run",
                "tests/fixtures/corpora/minimal_rest",
                "--out",
                str(tmp_path),
                "--llm-call-confirm-threshold",
                "0",
            ],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache")},
        )
        assert result.exit_code != 0
        assert "Re-run with --yes or --non-interactive" in result.output


def test_cli_max_calls_ceiling(tmp_path):
    """Verify that --max-llm-calls limits execution and aborts."""
    runner = CliRunner()
    from codeograph.llm.middleware.ceiling_llm_provider import CeilingLlmProvider

    mock_provider = CeilingLlmProvider(_build_mock_provider(), max_calls=1)

    with patch(
        "codeograph.llm.resolver.LlmProviderResolver.resolve",
        return_value=mock_provider,
    ):
        result = runner.invoke(
            cli,
            [
                "run",
                "tests/fixtures/corpora/minimal_rest",
                "--out",
                str(tmp_path),
                "--max-llm-calls",
                "1",
                "--yes",  # Bypass confirmation gate
            ],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache")},
        )
        assert result.exit_code != 0
        assert "ceiling" in result.output.lower()
