import tempfile
from pathlib import Path, PurePosixPath
from typing import cast

from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.provider import LlmProvider
from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig
from codeograph.renderers.typescript_nestjs.typescript_renderer import TypeScriptRenderer


def _make_renderer(config: TypeScriptConfig | None = None) -> TypeScriptRenderer:
    """Return a TypeScriptRenderer with a null provider (for policy-dispatch tests)."""
    return TypeScriptRenderer(
        config=config or TypeScriptConfig(),
        provider=cast(LlmProvider, None),
        prompt_loader=PromptLoader(Path(tempfile.mkdtemp())),
    )


class TestScaffoldSqliteBranch:
    """Scaffold templates must emit sqlite-shaped config for better-sqlite3."""

    def _render_scaffold(self, db_adapter: str) -> dict[PurePosixPath, bytes]:
        renderer = _make_renderer(TypeScriptConfig(db_adapter=db_adapter))  # type: ignore[arg-type]
        return renderer._render_scaffold([])

    def test_pg_emits_host_and_port(self):
        file_map = self._render_scaffold("pg")
        app_module = file_map[PurePosixPath("src/app.module.ts")].decode()
        assert "host:" in app_module
        assert "port:" in app_module
        assert "database:" in app_module

    def test_sqlite_emits_database_no_host_no_port(self):
        file_map = self._render_scaffold("better-sqlite3")
        app_module = file_map[PurePosixPath("src/app.module.ts")].decode()
        assert "database:" in app_module
        assert "host:" not in app_module
        assert "port:" not in app_module

    def test_sqlite_env_example_no_pg_vars(self):
        file_map = self._render_scaffold("better-sqlite3")
        env_example = file_map[PurePosixPath(".env.example")].decode()
        assert "DB_FILE" in env_example
        assert "DB_HOST" not in env_example
