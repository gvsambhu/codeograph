"""Decorator-based renderer registry and factory (ADR-008 Fork 2).

Usage — registering a renderer::

    from codeograph.renderers.registry import RendererRegistry

    @RendererRegistry.register("typescript")
    class TypeScriptRenderer(Renderer[TypeScriptConfig]):
        config_class = TypeScriptConfig
        ...

Usage — instantiating from raw config (pipeline / CLI)::

    renderer = RendererRegistry.build(
        target="typescript",
        raw_config={"db_layer": "typeorm", ...},
        provider=provider,
        prompt_loader=loader,
        concurrency=8,
    )

Design notes:
    - ``register()`` validates ``config_class`` at *decoration* time so
      misconfigured renderers are caught on import, not at runtime.
    - ``build()`` delegates config validation to Pydantic — callers receive a
      ``pydantic.ValidationError`` with field-level detail on bad config.
    - The registry is a module-level singleton; concurrent reads are safe
      because Python's GIL protects dict look-ups.  Writes only happen at
      import time (decoration), before any threads exist in a typical CLI run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codeograph.renderers.base import Renderer

if TYPE_CHECKING:
    from codeograph.llm.prompts.loader import PromptLoader
    from codeograph.llm.provider import LlmProvider

__all__ = ["RendererRegistry"]


class RendererRegistry:
    """Module-level registry that maps target names to renderer classes.

    All public methods are class-methods; the class is never instantiated.
    """

    _registry: dict[str, type[Renderer[Any]]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, target: str) -> Any:
        """Class decorator that registers a ``Renderer`` subclass.

        Args:
            target: Lower-case target language/framework name
                    (e.g. ``"typescript"``, ``"go"``).

        Returns:
            A decorator that validates and registers the class, then returns it
            unchanged so the decorated name stays importable as normal.

        Raises:
            TypeError: If the decorated class is not a ``Renderer`` subclass,
                       or if it does not declare a ``config_class`` ClassVar.
            ValueError: If ``target`` is already registered (prevents silent
                        shadowing when two modules both claim the same name).
        """

        def decorator(renderer_cls: type[Renderer[Any]]) -> type[Renderer[Any]]:
            if not (isinstance(renderer_cls, type) and issubclass(renderer_cls, Renderer)):
                raise TypeError(
                    f"@RendererRegistry.register({target!r}) can only decorate"
                    f" Renderer subclasses, got {renderer_cls!r}."
                )

            if not hasattr(renderer_cls, "config_class"):
                raise TypeError(
                    f"Renderer {renderer_cls.__name__!r} must declare"
                    f" 'config_class: ClassVar[type[BaseModel]]' before being"
                    f" registered as target {target!r}."
                )

            if target in cls._registry:
                existing = cls._registry[target].__name__
                raise ValueError(
                    f"Target {target!r} is already registered by {existing!r}.  Each target name must be unique."
                )

            cls._registry[target] = renderer_cls
            return renderer_cls

        return decorator

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        target: str,
        raw_config: dict[str, Any],
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        concurrency: int = 5,
    ) -> Renderer[Any]:
        """Instantiate the renderer for *target* from a raw config dict.

        Pydantic validates ``raw_config`` against the renderer's
        ``config_class``; callers receive ``pydantic.ValidationError`` on
        invalid input — no need for extra wrapping here.

        Args:
            target:       Registered target name (e.g. ``"typescript"``).
            raw_config:   Mapping of config field names → raw values, typically
                          parsed from TOML / YAML / CLI.
            provider:     LLM provider injected into the renderer.
            prompt_loader: Prompt loader injected into the renderer.
            concurrency:  Max concurrent LLM calls.  Defaults to 5.

        Returns:
            A fully-constructed ``Renderer`` instance ready to call
            ``.render()``.

        Raises:
            KeyError: If ``target`` is not registered.
            pydantic.ValidationError: If ``raw_config`` fails schema
                                      validation for the renderer's config class.
        """
        if target not in cls._registry:
            available = sorted(cls._registry)
            raise KeyError(
                f"No renderer registered for target {target!r}."
                f"  Available targets: {available or '(none registered yet)'}."
            )

        renderer_cls = cls._registry[target]
        config = renderer_cls.config_class(**raw_config)
        return renderer_cls(
            config=config,
            provider=provider,
            prompt_loader=prompt_loader,
            concurrency=concurrency,
        )

    # ------------------------------------------------------------------
    # Introspection helpers (used by CLI `codeograph render --list`)
    # ------------------------------------------------------------------

    @classmethod
    def targets(cls) -> list[str]:
        """Return sorted list of registered target names."""
        return sorted(cls._registry)

    @classmethod
    def clear(cls) -> None:
        """Remove all registrations.

        Intended **only** for test isolation — never call in production code.
        """
        cls._registry.clear()
