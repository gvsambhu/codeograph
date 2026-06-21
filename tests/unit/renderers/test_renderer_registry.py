"""Tests for RendererRegistry (M2 — ADR-008 Fork 2).

Tests registration, validation-at-decoration-time, and build() factory.
The registry is reset between tests using RendererRegistry.clear() to
avoid cross-test contamination.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from codeograph.renderers.base import Renderer
from codeograph.renderers.renderer_registry import RendererRegistry

# ---------------------------------------------------------------------------
# Minimal concrete renderer used only in this test module
# ---------------------------------------------------------------------------


class _MinimalConfig(BaseModel):
    value: str = "default"


class _MinimalRenderer(Renderer[_MinimalConfig]):
    config_class = _MinimalConfig

    def __init__(self, config, provider, prompt_loader, concurrency=5):
        self._config = config

    def render(self, graph, annotations):
        return {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset registry before and after every test."""
    RendererRegistry.clear()
    yield
    RendererRegistry.clear()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_targets(self):
        RendererRegistry.register("minimal")(_MinimalRenderer)
        assert "minimal" in RendererRegistry.targets()

    def test_duplicate_target_raises_value_error(self):
        RendererRegistry.register("minimal")(_MinimalRenderer)
        with pytest.raises(ValueError, match="already registered"):
            RendererRegistry.register("minimal")(_MinimalRenderer)

    def test_non_renderer_subclass_raises_type_error(self):
        class NotARenderer:
            pass

        with pytest.raises(TypeError, match="Renderer subclasses"):
            RendererRegistry.register("bad")(NotARenderer)

    def test_missing_config_class_raises_type_error(self):
        class RendererWithoutConfigClass(Renderer[_MinimalConfig]):
            # Deliberately omit config_class
            def __init__(self, config, provider, prompt_loader, concurrency=5):
                pass

            def render(self, graph, annotations):
                return {}

        with pytest.raises(TypeError, match="config_class"):
            RendererRegistry.register("noconfig")(RendererWithoutConfigClass)

    def test_decorator_returns_class_unchanged(self):
        result = RendererRegistry.register("minimal")(_MinimalRenderer)
        assert result is _MinimalRenderer


# ---------------------------------------------------------------------------
# build() factory tests
# ---------------------------------------------------------------------------


class TestBuild:
    def test_build_unknown_target_raises_key_error(self):
        with pytest.raises(KeyError, match="No renderer registered"):
            RendererRegistry.build(
                target="nonexistent",
                raw_config={},
                provider=None,  # type: ignore[arg-type]
                prompt_loader=None,  # type: ignore[arg-type]
            )

    def test_build_returns_renderer_instance(self):
        RendererRegistry.register("minimal")(_MinimalRenderer)
        renderer = RendererRegistry.build(
            target="minimal",
            raw_config={"value": "hello"},
            provider=None,  # type: ignore[arg-type]
            prompt_loader=None,  # type: ignore[arg-type]
        )
        assert isinstance(renderer, _MinimalRenderer)

    def test_build_invalid_config_raises_validation_error(self):
        # TODO(learner): add a config field with strict validation and confirm
        # that passing a bad value raises pydantic.ValidationError.
        #
        # Hint: add a field like `count: int = Field(ge=1)` to _MinimalConfig,
        # then call build() with {"count": -1} and assert ValidationError is raised.
        pass

    def test_build_applies_config_defaults(self):
        RendererRegistry.register("minimal")(_MinimalRenderer)
        renderer = RendererRegistry.build(
            target="minimal",
            raw_config={},  # no overrides — use defaults
            provider=None,  # type: ignore[arg-type]
            prompt_loader=None,  # type: ignore[arg-type]
        )
        assert isinstance(renderer, _MinimalRenderer)
        # TODO(learner): assert renderer._config.value == "default"


# ---------------------------------------------------------------------------
# Introspection tests
# ---------------------------------------------------------------------------


class TestIntrospection:
    def test_targets_returns_sorted_list(self):
        RendererRegistry.register("zebra")(_MinimalRenderer)

        class _OtherRenderer(_MinimalRenderer):
            pass

        RendererRegistry.register("alpha")(_OtherRenderer)
        assert RendererRegistry.targets() == ["alpha", "zebra"]

    def test_clear_empties_registry(self):
        RendererRegistry.register("minimal")(_MinimalRenderer)
        RendererRegistry.clear()
        assert RendererRegistry.targets() == []
