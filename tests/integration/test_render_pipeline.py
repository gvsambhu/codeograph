import asyncio
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from codeograph.graph.models.graph_schema import ClassNode
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.provider import LlmProvider
from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig
from codeograph.renderers.typescript_nestjs.typescript_renderer import TypeScriptRenderer
from codeograph.rendering.models import SelectionResult

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_renderer(config: TypeScriptConfig | None = None) -> TypeScriptRenderer:
    """Return a TypeScriptRenderer with a null provider (for policy-dispatch tests)."""
    return TypeScriptRenderer(
        config=config or TypeScriptConfig(),
        provider=cast(LlmProvider, None),
        prompt_loader=PromptLoader(Path(tempfile.mkdtemp())),
    )


def _make_class_node(
    fqcn: str = "com.example.orders.OrderService",
    stereotype: str | None = "Service",
    annotations: list[str] | None = None,
) -> ClassNode:
    return ClassNode(
        id=fqcn,
        name=fqcn.rsplit(".", 1)[-1],
        kind="class",
        modifiers=["public"],
        source_file="src/main/java/com/example/orders/OrderService.java",
        line_range=[1, 40],
        extraction_mode="ast",
        stereotype=stereotype,
        annotations=annotations or [],
    )


def _annotations_with_methods(fqcn: str, return_types: list[str]) -> dict[str, object]:
    """Build a minimal annotations dict whose methods use the given return types."""
    return {
        fqcn: {
            "annotation": {
                "methods": [{"return_type": rt} for rt in return_types],
            }
        }
    }


def test_render_group_basic():
    # 1. Build a minimal ClassNode + graph
    class_node = ClassNode(
        id="com.example.orders.OrderService",
        name="OrderService",
        kind="class",
        modifiers=["public"],
        source_file="src/main/java/com/example/orders/OrderService.java",
        line_range=[1, 40],
        extraction_mode="ast",
        annotations=[],
    )

    # 2. Build a minimal SelectionResult
    result = SelectionResult(
        selected=("com.example.orders.OrderService",),
        excluded=(),
        strategy="take_all",
        group_name="orders",
        cap=50,
        total_in_group=1,
        metrics_missing_count=0,
        high_count=0,
    )

    # 3. Build a mock node_map
    node_map = {"com.example.orders.OrderService": class_node}

    # 4. Build TypeScriptRenderer with a mock/null provider
    config = TypeScriptConfig()
    provider = cast(LlmProvider, None)
    prompt_loader = PromptLoader(Path(tempfile.mkdtemp()))

    renderer = TypeScriptRenderer(
        config=config,
        provider=provider,
        prompt_loader=prompt_loader,
    )

    # 5. Patch renderer._call_llm with stdlib unittest.mock (no pytest-mock dep)
    # _call_llm is async, so AsyncMock is required to make `await` work.
    canned_ts = "// canned\nexport class OrderService {}\n"
    with patch.object(renderer, "_call_llm", new=AsyncMock(return_value=canned_ts)):
        # 6. Call _render_group
        semaphore = asyncio.Semaphore(5)
        file_map = asyncio.run(renderer._render_group(result, {}, node_map, semaphore))

    # 7. Assert
    has_ts = any(path.name.endswith(".ts") and not path.name.endswith(".module.ts") for path in file_map.keys())
    assert has_ts

    module_path = PurePosixPath("src/orders/orders.module.ts")
    assert module_path in file_map

    module_content = file_map[module_path].decode("utf-8")
    assert module_content.startswith("/**")


# ---------------------------------------------------------------------------
# Issue #3 — WebFlux translate_mono_only must refuse Flux<T> classes
# ---------------------------------------------------------------------------


class TestWebFluxTranslateMonoOnly:
    """ADR-010 Fork 9: translate_mono_only refuses Flux, passes Mono."""

    def _render_class_sync(self, renderer: TypeScriptRenderer, class_node: ClassNode, annotations: dict[str, Any]):
        """Run _render_class in a fresh event loop (avoids nested-loop issues in tests)."""
        return asyncio.run(renderer._render_class(class_node, "orders", annotations))

    def test_flux_only_is_refused(self):
        renderer = _make_renderer(TypeScriptConfig(webflux_policy="translate_mono_only"))
        node = _make_class_node()
        annotations = _annotations_with_methods(node.id, ["Flux<Order>"])
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            result = self._render_class_sync(renderer, node, annotations)
        assert result is None

    def test_mono_only_proceeds(self):
        renderer = _make_renderer(TypeScriptConfig(webflux_policy="translate_mono_only"))
        node = _make_class_node()
        annotations = _annotations_with_methods(node.id, ["Mono<Order>"])
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            result = self._render_class_sync(renderer, node, annotations)
        assert result is not None

    def test_both_mono_and_flux_is_refused(self):
        renderer = _make_renderer(TypeScriptConfig(webflux_policy="translate_mono_only"))
        node = _make_class_node()
        annotations = _annotations_with_methods(node.id, ["Mono<Order>", "Flux<Order>"])
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            result = self._render_class_sync(renderer, node, annotations)
        assert result is None


# ---------------------------------------------------------------------------
# Issue #4 — Security silent_skip must NOT inject a TODO hint
# ---------------------------------------------------------------------------


class TestSecurityFeaturePolicy:
    """ADR-010 Fork 9: security policy dispatch — refuse/stub_todo/silent_skip."""

    def _render_class_sync(self, renderer: TypeScriptRenderer, class_node: ClassNode, annotations: dict[str, Any]):
        return asyncio.run(renderer._render_class(class_node, "orders", annotations))

    def _secured_node(self) -> ClassNode:
        return _make_class_node(annotations=["PreAuthorize"])

    def test_refuse_returns_none(self):
        renderer = _make_renderer(TypeScriptConfig(security_feature_policy="refuse"))
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            result = self._render_class_sync(renderer, self._secured_node(), {})
        assert result is None

    def test_stub_todo_injects_hint(self):
        renderer = _make_renderer(TypeScriptConfig(security_feature_policy="stub_todo"))
        captured: list[dict[str, Any]] = []

        async def capture_hints(_node, _ann, hints):
            captured.append(dict(hints))
            return "export class X {}"

        with patch.object(renderer, "_call_llm", new=capture_hints):
            self._render_class_sync(renderer, self._secured_node(), {})

        assert captured, "Expected _call_llm to be called"
        assert "security_hint" in captured[0]

    def test_silent_skip_no_hint(self):
        renderer = _make_renderer(TypeScriptConfig(security_feature_policy="silent_skip"))
        captured: list[dict[str, Any]] = []

        async def capture_hints(_node, _ann, hints):
            captured.append(dict(hints))
            return "export class X {}"

        with patch.object(renderer, "_call_llm", new=capture_hints):
            self._render_class_sync(renderer, self._secured_node(), {})

        assert captured, "Expected _call_llm to be called"
        assert "security_hint" not in captured[0]


# ---------------------------------------------------------------------------
# Issue #1 — File-name role suffix: Service → .service.ts
# ---------------------------------------------------------------------------


class TestRoleFileSuffix:
    """Rendered file paths must carry the role-derived suffix."""

    def test_service_class_produces_service_ts(self):
        config = TypeScriptConfig()
        renderer = _make_renderer(config)
        node = _make_class_node(stereotype="Service")
        result = SelectionResult(
            selected=(node.id,),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=1,
            metrics_missing_count=0,
            high_count=0,
        )
        node_map = {node.id: node}
        canned_ts = "export class OrderService {}\n"
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value=canned_ts)):
            semaphore = asyncio.Semaphore(5)
            file_map = asyncio.run(renderer._render_group(result, {}, node_map, semaphore))

        service_files = [p for p in file_map if p.name.endswith(".service.ts")]
        assert service_files, "Expected at least one .service.ts file"

        # Domain module must list the service class
        module_bytes = file_map[PurePosixPath("src/orders/orders.module.ts")]
        assert b"OrderService" in module_bytes

    def test_controller_class_produces_controller_ts(self):
        renderer = _make_renderer()
        node = _make_class_node(
            fqcn="com.example.orders.OrderController",
            stereotype="RestController",
        )
        result = SelectionResult(
            selected=(node.id,),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=1,
            metrics_missing_count=0,
            high_count=0,
        )
        node_map = {node.id: node}
        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            semaphore = asyncio.Semaphore(5)
            file_map = asyncio.run(renderer._render_group(result, {}, node_map, semaphore))

        controller_files = [p for p in file_map if p.name.endswith(".controller.ts")]
        assert controller_files


# ---------------------------------------------------------------------------
# DC3-03 — per-class LLM failure must not abort the whole group
# DC3-04 — duplicate path within a group must raise a loud ValueError
# DC3-05 — refused class must record the named refuse reason (ADR-010 D-010-2)
# ---------------------------------------------------------------------------


class TestRenderErrorHandling:
    """D-008-2/5 + D-010-2 Confirmations: error isolation, dup detection, refuse audit."""

    def _render_group_sync(
        self,
        renderer: TypeScriptRenderer,
        result: SelectionResult,
        annotations: dict[str, Any],
        node_map: dict[str, Any],
    ) -> dict[str, Any]:
        semaphore = asyncio.Semaphore(5)
        return asyncio.run(renderer._render_group(result, annotations, node_map, semaphore))

    # -- DC3-03 ----------------------------------------------------------------

    def test_llm_error_skips_failed_class_others_still_render(self):
        """One LLM error must not abort the group — the surviving class still renders."""
        renderer = _make_renderer()

        ok_node = _make_class_node("com.example.orders.OrderService", stereotype="Service")
        fail_node = _make_class_node("com.example.orders.PaymentService", stereotype="Service")

        result = SelectionResult(
            selected=(ok_node.id, fail_node.id),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=2,
            metrics_missing_count=0,
            high_count=0,
        )
        node_map = {ok_node.id: ok_node, fail_node.id: fail_node}

        async def selective_llm(node, ann, hints):
            if node.id == fail_node.id:
                raise RuntimeError("simulated LLM failure")
            return "export class OrderService {}\n"

        with patch.object(renderer, "_call_llm", new=selective_llm):
            file_map = self._render_group_sync(renderer, result, {}, node_map)

        assert any("order-service" in str(p) for p in file_map), "Successful class must appear in file_map"
        assert not any("payment-service" in str(p) for p in file_map), "Failed class must be absent from file_map"

    # -- DC3-04 ----------------------------------------------------------------

    def test_duplicate_intra_group_path_raises_value_error(self):
        """Two classes in the same group that resolve to the same path raise ValueError."""
        renderer = _make_renderer()

        # Same simple name + same stereotype in the same group → identical output path
        node_a = _make_class_node("com.example.orders.OrderService", stereotype="Service")
        node_b = _make_class_node("com.example.payments.OrderService", stereotype="Service")

        result = SelectionResult(
            selected=(node_a.id, node_b.id),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=2,
            metrics_missing_count=0,
            high_count=0,
        )
        node_map = {node_a.id: node_a, node_b.id: node_b}

        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            with pytest.raises(ValueError, match="Duplicate render output path"):
                self._render_group_sync(renderer, result, {}, node_map)

    # -- DC3-05 ----------------------------------------------------------------

    def test_security_refuse_excludes_class_from_output(self):
        """A class refused by security_feature_policy must not appear in the file map."""
        renderer = _make_renderer(TypeScriptConfig(security_feature_policy="refuse"))

        secured_node = _make_class_node(
            "com.example.orders.OrderController",
            stereotype="RestController",
            annotations=["PreAuthorize"],
        )
        result = SelectionResult(
            selected=(secured_node.id,),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=1,
            metrics_missing_count=0,
            high_count=0,
        )
        node_map = {secured_node.id: secured_node}

        with patch.object(renderer, "_call_llm", new=AsyncMock(return_value="export class X {}")):
            file_map = self._render_group_sync(renderer, result, {}, node_map)

        assert not any(str(p).endswith(".controller.ts") for p in file_map), (
            "Security-refused class must not produce a .controller.ts file"
        )

    def test_security_refuse_reason_named_security(self):
        """dispatch_feature_policies must return the string 'security' when refusing a secured class."""
        from codeograph.renderers.typescript_nestjs.feature_policies import dispatch_feature_policies

        secured_node = _make_class_node(annotations=["PreAuthorize"])
        config = TypeScriptConfig(security_feature_policy="refuse")
        result = dispatch_feature_policies(secured_node, {}, config)

        assert result == "security", f"Expected refuse reason 'security', got {result!r}"
