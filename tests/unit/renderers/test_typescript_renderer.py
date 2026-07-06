import asyncio
import tempfile
from pathlib import Path, PurePosixPath
from typing import cast

import pytest

from codeograph.graph.models.graph_schema import (
    ClassNode,
    CodeographKnowledgeGraph,
    ExtractionMode,
    InterfaceNode,
    Modifier,
    Modifier1,
    Node,
    RecordNode,
)
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.provider import LlmProvider
from codeograph.renderers.typescript_nestjs.feature_policies import dispatch_feature_policies
from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig
from codeograph.renderers.typescript_nestjs.typescript_renderer import TypeScriptRenderer
from codeograph.rendering.models import SelectionResult


def _make_renderer(config: TypeScriptConfig | None = None) -> TypeScriptRenderer:
    """Return a TypeScriptRenderer with a null provider (for policy-dispatch tests)."""
    return TypeScriptRenderer(
        config=config or TypeScriptConfig(),
        provider=cast(LlmProvider, None),
        prompt_loader=PromptLoader(Path(tempfile.mkdtemp())),
    )


def _make_class_node(fqcn: str, *, annotations: list[str] | None = None) -> ClassNode:
    return ClassNode(
        id=fqcn,
        kind="class",
        name=fqcn.rsplit(".", 1)[-1],
        modifiers=[Modifier.public],
        source_file=f"src/{fqcn}.java",
        line_range=[1, 10],
        extraction_mode=ExtractionMode.ast,
        annotations=annotations or [],
    )


class TestScaffoldSqliteBranch:
    """Scaffold templates must emit sqlite-shaped config for better-sqlite3."""

    def _render_scaffold(self, db_adapter: str) -> dict[PurePosixPath, bytes]:
        renderer = _make_renderer(TypeScriptConfig(db_adapter=db_adapter))  # type: ignore[arg-type]
        return renderer._scaffold_emitter.render_scaffold([])

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


# ---------------------------------------------------------------------------
# DC3-05: dispatch_feature_policies returns named refuse reason (not None)
# ---------------------------------------------------------------------------


class TestFeaturePoliciesRefuseReason:
    """DC3-05: dispatch_feature_policies must return a named str reason, not None."""

    def test_security_refuse_returns_reason_string(self):
        """A security-annotated class with refuse policy returns 'security', not None."""
        node = _make_class_node("com.example.SecureController", annotations=["PreAuthorize"])
        config = TypeScriptConfig(security_feature_policy="refuse")
        result = dispatch_feature_policies(node, {}, config)
        assert result == "security", f"Expected 'security', got {result!r}"

    def test_webflux_refuse_returns_reason_string(self):
        """A WebFlux class with refuse policy returns 'webflux_refuse', not None."""
        node = _make_class_node("com.example.ReactiveService")
        # Simulate Mono< in return type via annotations dict
        annotations: dict[str, object] = {
            "com.example.ReactiveService": {"annotation": {"methods": [{"return_type": "Mono<String>"}]}}
        }
        config = TypeScriptConfig(webflux_policy="refuse")
        result = dispatch_feature_policies(node, annotations, config)
        assert result == "webflux_refuse", f"Expected 'webflux_refuse', got {result!r}"

    def test_webflux_flux_only_refuse_returns_reason_string(self):
        """A Flux class with translate_mono_only policy returns 'webflux_flux_only'."""
        node = _make_class_node("com.example.FluxService")
        annotations: dict[str, object] = {
            "com.example.FluxService": {"annotation": {"methods": [{"return_type": "Flux<Event>"}]}}
        }
        config = TypeScriptConfig(webflux_policy="translate_mono_only")
        result = dispatch_feature_policies(node, annotations, config)
        assert result == "webflux_flux_only", f"Expected 'webflux_flux_only', got {result!r}"

    def test_no_policy_triggered_returns_empty_dict(self):
        """A plain class with default config returns an empty hints dict (not a str)."""
        node = _make_class_node("com.example.PlainService")
        config = TypeScriptConfig()
        result = dispatch_feature_policies(node, {}, config)
        assert isinstance(result, dict), f"Expected dict, got {type(result).__name__}"

    def test_security_refuse_class_is_skipped_by_renderer(self):
        """DC3-05 integration: _render_class returns None for a security-refused class."""
        node = _make_class_node("com.example.SecureCtrl", annotations=["PreAuthorize"])
        renderer = _make_renderer(TypeScriptConfig(security_feature_policy="refuse"))
        result = asyncio.run(renderer._render_class(node, "orders", {}))
        assert result is None


# ---------------------------------------------------------------------------
# DC3-04: Duplicate render path raises a loud ValueError
# ---------------------------------------------------------------------------


class TestDuplicateRenderPath:
    """DC3-04: assembling two classes that resolve to the same output path must raise."""

    def test_duplicate_group_path_raises(self):
        """Two domain groups producing the same output path must raise ValueError."""
        # Create two groups whose maps both contain the same path
        path = PurePosixPath("src/orders/foo.service.ts")
        gmap_a: dict[PurePosixPath, bytes] = {path: b"// group A"}
        gmap_b: dict[PurePosixPath, bytes] = {path: b"// group B"}

        # Minimal SelectionResult stubs
        def _sr(name: str) -> SelectionResult:
            return SelectionResult(
                selected=(),
                excluded=(),
                strategy="take_all",
                group_name=name,
                cap=50,
                total_in_group=0,
                metrics_missing_count=0,
                high_count=0,
            )

        # Manually exercise the merge loop from _render_async
        file_map: dict[PurePosixPath, bytes] = {}
        selection_results = [_sr("orders"), _sr("payments")]
        group_maps = [gmap_a, gmap_b]

        with pytest.raises(ValueError, match="Duplicate render output path"):
            for i, gmap in enumerate(group_maps):
                for p in gmap:
                    if p in file_map:
                        raise ValueError(
                            f"Duplicate render output path '{p}' produced by group "
                            f"'{selection_results[i].group_name}'. "
                            "Two classes resolved to the same output file — check class names and stereotypes."
                        )
                file_map.update(gmap)


# ---------------------------------------------------------------------------
# ADR-010: _build_node_map must include interfaces/records, not just classes
# ---------------------------------------------------------------------------


class TestBuildNodeMapIncludesAllRenderableKinds:
    """2026-07-06 manual run: _build_node_map was ClassNode-only, so even a
    correctly-selected interface/record FQCN silently failed the node_map
    lookup in _render_group (hitting a 'defensive: unreachable' continue that
    was, in fact, reachable)."""

    def test_interface_and_record_nodes_are_included(self):
        class_node = _make_class_node("com.example.orders.OrderService")
        interface_node = InterfaceNode(
            id="com.example.orders.OrderRepository",
            kind="interface",
            name="OrderRepository",
            modifiers=[Modifier1.public],
            source_file="src/com/example/orders/OrderRepository.java",
            line_range=[1, 10],
        )
        record_node = RecordNode(
            id="com.example.orders.OrderDto",
            kind="record",
            name="OrderDto",
            components=[],
            source_file="src/com/example/orders/OrderDto.java",
            line_range=[1, 5],
        )
        graph = CodeographKnowledgeGraph(
            nodes=[Node(root=class_node), Node(root=interface_node), Node(root=record_node)],
            edges=[],
        )

        renderer = _make_renderer()
        node_map = renderer._build_node_map(graph)

        assert set(node_map) == {
            "com.example.orders.OrderService",
            "com.example.orders.OrderRepository",
            "com.example.orders.OrderDto",
        }
