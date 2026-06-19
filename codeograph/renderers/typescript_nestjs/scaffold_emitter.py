"""Scaffold emission logic for TypeScript/NestJS rendering."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from jinja2 import Environment, PackageLoader, StrictUndefined

from codeograph.renderers.typescript_nestjs.helpers import to_pascal_case

if TYPE_CHECKING:
    from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig
    from codeograph.rendering.models import SelectionResult


# Package name for Jinja2 PackageLoader
_TEMPLATE_PACKAGE = "codeograph.renderers.typescript_nestjs"
_TEMPLATE_DIR = "templates/scaffold"

# NestJS version pinned per Q1 decision
_NESTJS_VERSION = "^10.4.0"
_TYPEORM_VERSION = "^0.3.20"
_PG_VERSION = "^8.12.0"
_BETTER_SQLITE3_VERSION = "^9.6.0"


def _db_adapter_info(adapter: str) -> tuple[str, str]:
    """Return ``(npm_package_name, version_constraint)`` for *adapter*."""
    if adapter == "pg":
        return "pg", _PG_VERSION
    if adapter == "better-sqlite3":
        return "better-sqlite3", _BETTER_SQLITE3_VERSION
    raise ValueError(f"Unknown db_adapter: {adapter!r}")


class ScaffoldEmitter:
    """Handles Jinja2 template rendering for NestJS project scaffolding."""

    def __init__(self, config: TypeScriptConfig) -> None:
        self._config = config
        self._jinja: Environment = Environment(
            loader=PackageLoader(_TEMPLATE_PACKAGE, _TEMPLATE_DIR),
            undefined=StrictUndefined,
            autoescape=False,
        )

    def render_scaffold(self, domain_groups: list[dict[str, str]]) -> dict[PurePosixPath, bytes]:
        """Emit the NestJS project skeleton."""
        project_name = "app"  # TODO: derive from graph or config
        db_adapter = self._config.db_adapter
        db_adapter_pkg, db_adapter_ver = _db_adapter_info(db_adapter)

        ctx: dict[str, object] = {
            "project_name": project_name,
            "domain_groups": domain_groups,
            "db_adapter": db_adapter,
            "db_adapter_package": db_adapter_pkg,
            "db_adapter_version": db_adapter_ver,
            "strict": self._config.strict,
        }

        _emit = self._emit_template
        return {
            PurePosixPath("package.json"): _emit("package.json.j2", ctx),
            PurePosixPath("tsconfig.json"): _emit("tsconfig.json.j2", ctx),
            PurePosixPath("tsconfig.build.json"): _emit("tsconfig.build.json.j2", ctx),
            PurePosixPath("nest-cli.json"): _emit("nest-cli.json.j2", ctx),
            PurePosixPath(".gitignore"): _emit("gitignore.j2", ctx),
            PurePosixPath(".env.example"): _emit("env.example.j2", ctx),
            PurePosixPath("src/main.ts"): _emit("main.ts.j2", ctx),
            PurePosixPath("src/app.module.ts"): _emit("app.module.ts.j2", ctx),
        }

    def render_domain_module(
        self,
        result: SelectionResult,
        group_file_map: dict[PurePosixPath, bytes],
    ) -> bytes | None:
        """Emit a NestJS module barrel for *result.group_name*."""
        controllers = []
        services = []
        entities = []
        repositories = []

        for path in group_file_map.keys():
            if path.name.endswith(".controller.ts"):
                controllers.append({"class_name": to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".service.ts"):
                services.append({"class_name": to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".entity.ts"):
                entities.append({"class_name": to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".repository.ts"):
                repositories.append({"class_name": to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})

        context: dict[str, object] = {
            "group_name": result.group_name,
            "module_class_name": to_pascal_case(result.group_name) + "Module",
            "selected_count": result.total_in_group,
            "selection_strategy": result.strategy,
            "controllers": controllers,
            "services": services,
            "entities": entities,
            "repositories": repositories,
        }
        return self._emit_template("domain.module.ts.j2", context)

    def _emit_template(self, template_name: str, context: dict[str, object]) -> bytes:
        """Render one Jinja2 template to bytes."""
        tpl = self._jinja.get_template(template_name)
        return tpl.render(**context).encode("utf-8")
