"""Renderer ABC and CompileCheck value object (ADR-008 Forks 1, 3, 5).

Every target-language renderer:
  1. Subclasses ``Renderer[C]`` where ``C`` is its Pydantic config class.
  2. Declares ``config_class: ClassVar[type[BaseModel]]`` pointing at ``C``.
  3. Implements ``render(graph, annotations) -> dict[PurePosixPath, bytes]``.
  4. Optionally overrides ``compile_checks()`` to declare eval hook commands.
  5. Registers itself with ``@RendererRegistry.register("<target>")``
     (imported from ``codeograph.renderers.registry``).

The constructor parameter order is locked (per ADR-008 Fork 5):
    ``(config: C, provider: LlmProvider, prompt_loader: PromptLoader, concurrency: int = 5)``
so consumers recognise the same shape as NodeAnnotator and CorpusSynthesizer.

Migration note (streaming, deferred per ADR-008):
    When projected output exceeds ~100 MB OR per-file progress UX is needed,
    add a non-abstract ``render_streaming(...) -> Iterator[RenderedFile]``.
    Default impl collects the dict and yields entries; streaming-native renderers
    override it.  Migration is purely additive — existing renderers do not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, ClassVar, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph
    from codeograph.llm.prompts.loader import PromptLoader
    from codeograph.llm.provider import LlmProvider

    # LlmAnnotations is the dict produced by Pass 1 / NodeAnnotator.
    # Typed as Any-compatible dict here to avoid a hard dependency on pass1 schemas;
    # concrete renderers narrow the type in their own implementation.
    LlmAnnotations = dict[str, object]

__all__ = ["CompileCheck", "Renderer"]

C = TypeVar("C", bound=BaseModel)


@dataclass(frozen=True)
class CompileCheck:
    """Declarative description of one compile / typecheck command (ADR-008 Fork 3).

    The eval framework (DC4) iterates ``renderer.compile_checks()``,
    preflights ``required_tools`` via ``shutil.which``, runs each command
    with ``subprocess.run``, and records pass / skip / fail in the scorecard.

    Attributes:
        name:              Human-readable label shown in the scorecard row.
        cmd:               Command tuple passed to ``subprocess.run``.
        workdir:           Working directory relative to the rendered output root.
                           Defaults to the root itself.
        required_tools:    Tool names to preflight via ``shutil.which``.
                           A missing tool produces a recorded ``skip``, not a crash.
        pass_on_exit_codes: Exit codes that count as a pass.  Defaults to ``(0,)``.
    """

    name: str
    cmd: tuple[str, ...]
    workdir: PurePosixPath = field(default_factory=lambda: PurePosixPath("."))
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    pass_on_exit_codes: tuple[int, ...] = field(default_factory=lambda: (0,))


class Renderer(ABC, Generic[C]):  # noqa: UP046 — ADR-008 uses Generic[C]; py3.12 syntax deferred
    """Abstract base for all target-language renderers (ADR-008 Forks 1, 2, 5).

    Type parameter ``C`` is the renderer's Pydantic config class.
    ``RendererRegistry`` validates at decoration time that the concrete class
    declares ``config_class`` and that the generic parameter matches.

    Subclass pattern::

        @RendererRegistry.register("typescript")
        class TypeScriptRenderer(Renderer[TypeScriptConfig]):
            config_class = TypeScriptConfig

            def __init__(
                self,
                config: TypeScriptConfig,
                provider: LlmProvider,
                prompt_loader: PromptLoader,
                concurrency: int = 5,
            ) -> None:
                self._config = config
                self._provider = provider
                self._prompts = prompt_loader
                self._concurrency = concurrency

            def render(self, graph, annotations):
                ...
    """

    #: Each concrete renderer MUST declare this as a ClassVar pointing at its
    #: Pydantic config class.  RendererRegistry validates this at decoration time.
    config_class: ClassVar[type[BaseModel]]

    @abstractmethod
    def __init__(
        self,
        config: C,
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        concurrency: int = 5,
    ) -> None:
        """Construct the renderer with injected collaborators.

        Parameter order is locked (ADR-008 Fork 5) — mirrors NodeAnnotator and
        CorpusSynthesizer so all LLM-using passes share one mental model.
        """

    @abstractmethod
    def render(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: dict[str, object],
    ) -> dict[PurePosixPath, bytes]:
        """Translate ``(graph, annotations)`` into a file map.

        Returns:
            A ``{relative_path: file_bytes}`` mapping.  The *caller* (pipeline
            or ``codeograph render`` CLI) is responsible for writing the bytes to
            disk.  The renderer is a pure transformation — it never touches the
            filesystem.

        The returned paths MUST be ``PurePosixPath`` with POSIX separators so
        the pipeline can write them under any output directory without OS-specific
        path munging.
        """

    def compile_checks(self) -> list[CompileCheck]:
        """Declare compile / typecheck commands for the eval framework (ADR-008 Fork 3).

        Default returns an empty list — the renderer opts out of eval.
        Override to return one or more :class:`CompileCheck` instances.

        The eval framework (DC4) is responsible for invoking these; the renderer
        only declares *what* to run.  See ``CompileCheck`` docstring for field
        semantics.
        """
        return []
