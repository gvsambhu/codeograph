"""Smoke tests for `codeograph render --force` directory-clearing behaviour (Issue #5).

All LLM / provider / settings dependencies are patched at their canonical
module paths because render_cli uses lazy imports inside the function body.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

from click.testing import CliRunner, Result

from codeograph.cli.render import render_cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_from_dir(tmp_path: Path) -> Path:
    """Create a minimal --from directory with a valid 2.0.0 manifest.

    The render command reads the existing manifest via ``manifest_io.read``
    and adds the ``compile_checks`` top-level pointer. Before B5 the
    manifest block was a no-op for tests (no manifest existed) and the
    post-render manifest-update path was never exercised; after B5 the
    helper provides the manifest so the path runs end-to-end.
    """
    from_dir = tmp_path / "from"
    from_dir.mkdir()
    (from_dir / "graph.json").write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    (from_dir / "llm-annotations.json").write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": "2.0.0",
        "codeograph_version": "test",
        "source_path": str(from_dir),
        "corpus_id": "test",
        "run_id": "2026-06-08T00-00-00Z-000000",
        "llm_skipped": False,
        "artefacts": {
            "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
            "llm_annotations": {
                "path": "llm-annotations.json",
                "schema_version": "1.0.0",
                "sha256": "a" * 64,
            },
        },
    }
    (from_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8", newline="")
    return from_dir


def _render_patches(tmp_path: Path, file_map: dict[str, bytes]):
    """Return the stack of patches needed to bypass the full LLM/provider stack.

    Patches are applied at their canonical module paths because render_cli
    uses lazy ``from x import y`` inside the function.
    """
    mock_renderer = MagicMock()
    mock_renderer.render.return_value = file_map

    mock_settings = MagicMock()
    mock_settings.anthropic_api_key = None
    mock_settings.cache_dir = tmp_path / "cache"
    mock_settings.cache_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.llm_provider = "anthropic"
    mock_settings.llm_model = "claude-3-5-haiku-20241022"
    mock_settings.llm_model_fast = None
    mock_settings.llm_model_deep = None
    mock_settings.llm_model_render = None
    mock_settings.llm_concurrency = 1

    return [
        patch("codeograph.config.settings.Settings", return_value=mock_settings),
        patch("codeograph.llm.providers.anthropic_provider.AnthropicProvider", return_value=MagicMock()),
        patch("codeograph.llm.cache.sqlite_backend.SQLiteCacheBackend", return_value=MagicMock()),
        patch("codeograph.telemetry.jsonl_emitter.JsonlEmitter", return_value=MagicMock()),
        patch("codeograph.llm.middleware.retry_policy.RetryPolicy", return_value=MagicMock()),
        patch("codeograph.llm.factory.build_default_stack", return_value=MagicMock()),
        patch("codeograph.renderers.RendererRegistry.build", return_value=mock_renderer),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestForceFlag:
    def _invoke(self, tmp_path: Path, out_dir: Path, extra_args: tuple[str, ...] = ()) -> Result:
        from_dir = _minimal_from_dir(tmp_path)
        file_map = {PurePosixPath("src/orders/order.service.ts"): b"export class OrderService {}"}
        patches = _render_patches(tmp_path, file_map)
        runner = CliRunner()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            return runner.invoke(
                render_cli,
                ["--from", str(from_dir), "--out", str(out_dir), *extra_args],
            )

    def test_force_clears_stale_file(self, tmp_path):
        """--force on a non-empty out dir removes pre-existing files before writing."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        stale = out_dir / "stale.ts"
        stale.write_text("// stale", encoding="utf-8")

        result = self._invoke(tmp_path, out_dir, extra_args=["--force"])

        assert result.exit_code == 0, result.output
        assert not stale.exists(), "Stale file should have been removed by --force"
        assert (out_dir / "src" / "orders" / "order.service.ts").exists()

    def test_force_empty_dir_is_noop_clear(self, tmp_path):
        """--force on an empty out dir proceeds without error."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()  # exists but empty

        result = self._invoke(tmp_path, out_dir, extra_args=["--force"])

        assert result.exit_code == 0, result.output
        assert (out_dir / "src" / "orders" / "order.service.ts").exists()

    def test_no_force_non_empty_raises_usage_error(self, tmp_path):
        """Without --force, a non-empty out dir must produce a UsageError."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "existing.ts").write_text("x", encoding="utf-8")

        result = self._invoke(tmp_path, out_dir)  # no --force

        assert result.exit_code != 0
        assert "non-empty" in result.output.lower() or "force" in result.output.lower()
