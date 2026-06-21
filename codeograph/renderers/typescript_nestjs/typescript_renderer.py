"""TypeScriptRenderer — NestJS/TypeScript rendering pass (ADR-008, ADR-010).

Self-registers with RendererRegistry at import time:

    @RendererRegistry.register("typescript")
    class TypeScriptRenderer(Renderer[TypeScriptConfig]): ...

Rendering pipeline (high-level):

    1. ClassSelector partitions graph classes into domain groups and applies
       the ADR-009 budget cap (M4).
    2. For each selected class, the renderer dispatches to the LLM using the
       render prompt (``prompts/render_file/v1.md``).
    3. Feature policies (ADR-010 Fork 9) are applied before dispatching —
       refused classes are skipped, stub_with_todo classes get a canned stub.
    4. Jinja2 scaffold templates (M6) emit the NestJS project skeleton.
    5. All file bytes are collected into a ``dict[PurePosixPath, bytes]``
       and returned to the caller.  The renderer never touches the filesystem.

LLM call concurrency is capped at ``self._concurrency`` using asyncio
``Semaphore`` (same pattern as NodeAnnotator — see ADR-014).

Learning notes for the implementer:
    - The render prompt body lives in ``prompts/render_file/v1.md`` (M8).
      That is the learner's primary writing task for DC3.
    - Feature-policy dispatch (step 3) is where ADR-010 §4 becomes code —
      the WebFlux detection pattern is scaffolded with a TODO(learner) below.
    - asyncio concurrency pattern: Semaphore + gather is wired; ``_call_llm``
      shows the same ``asyncio.to_thread`` idiom as NodeAnnotator.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar

from codeograph.llm.models import CacheHint, Message, Tier
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render as render_prompt
from codeograph.renderers.base import Renderer
from codeograph.renderers.models import CompileCheck
from codeograph.renderers.renderer_registry import RendererRegistry
from codeograph.renderers.typescript_nestjs.feature_policies import dispatch_feature_policies
from codeograph.renderers.typescript_nestjs.helpers import (
    stereotype_to_role_suffix,
    to_kebab_case,
    to_pascal_case,
)
from codeograph.renderers.typescript_nestjs.models import RenderedSource
from codeograph.renderers.typescript_nestjs.scaffold_emitter import ScaffoldEmitter
from codeograph.renderers.typescript_nestjs.typescript_config import TypeScriptConfig
from codeograph.rendering.base import DomainGrouping
from codeograph.rendering.class_selector import ClassSelector
from codeograph.rendering.manual_mapping_grouping import ManualMappingGrouping
from codeograph.rendering.models import SelectionResult
from codeograph.rendering.package_prefix_grouping import PackagePrefixGrouping

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import ClassNode, CodeographKnowledgeGraph
    from codeograph.llm.provider import LlmProvider

__all__ = ["TypeScriptRenderer"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


@RendererRegistry.register("typescript")
class TypeScriptRenderer(Renderer[TypeScriptConfig]):  # noqa: UP046
    """Render a Spring Boot graph to a TypeScript/NestJS project.

    Constructor parameter order is locked per ADR-008 Fork 5::

        TypeScriptRenderer(config, provider, prompt_loader, concurrency=5)
    """

    config_class: ClassVar[type[TypeScriptConfig]] = TypeScriptConfig

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

        self._scaffold_emitter = ScaffoldEmitter(config)

        # Package-local PromptLoader for the render prompt.
        # Separate from self._prompts (which points at the main codeograph/prompts/).
        # Will raise PromptLoadError until the learner writes the prompt body (M8)
        # and runs scripts/update_prompt_hash_pins.py.
        self._render_prompts: PromptLoader = PromptLoader(Path(__file__).parent / "prompts")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def render(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: dict[str, object],
    ) -> dict[PurePosixPath, bytes]:
        """Entry point: translate ``(graph, annotations)`` to a file map.

        Returns:
            ``{relative_posix_path: file_bytes}`` for every file in the
            generated NestJS project.  The caller writes these to disk.
        """
        return asyncio.run(self._render_async(graph, annotations))

    def compile_checks(self) -> list[CompileCheck]:
        """Declare tsc and npm install as eval-framework compile hooks."""
        return [
            CompileCheck(
                name="npm install",
                cmd=("npm", "install", "--prefer-offline"),
                workdir=PurePosixPath("."),
                required_tools=("npm",),
            ),
            CompileCheck(
                name="tsc --noEmit",
                cmd=("npx", "tsc", "--noEmit"),
                workdir=PurePosixPath("."),
                required_tools=("npx",),
            ),
        ]

    # ------------------------------------------------------------------
    # Async rendering pipeline
    # ------------------------------------------------------------------

    async def _render_async(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: dict[str, object],
    ) -> dict[PurePosixPath, bytes]:
        """Orchestrate selection → policy dispatch → LLM calls → scaffold."""
        file_map: dict[PurePosixPath, bytes] = {}

        # Build fqcn → ClassNode lookup for fast per-class access.
        node_map = self._build_node_map(graph)

        # Step 1 — class selection (ADR-009 three-tier ladder)
        selection_results = self._select_classes(graph)

        # Step 2 — LLM rendering with concurrency cap
        semaphore = asyncio.Semaphore(self._concurrency)
        render_tasks = [self._render_group(result, annotations, node_map, semaphore) for result in selection_results]
        # DC3-03: return_exceptions=True prevents one failing group from aborting all others.
        # Per-class isolation is handled inside _render_group itself.
        group_maps: list[dict[PurePosixPath, bytes] | BaseException] = await asyncio.gather(
            *render_tasks, return_exceptions=True
        )

        for i, gmap in enumerate(group_maps):
            if isinstance(gmap, BaseException):
                # An entire group failed unexpectedly — log and skip it.
                group_name = selection_results[i].group_name
                logger.error("Render group '%s' failed entirely: %s", group_name, gmap)
                continue
            # DC3-04: detect duplicate output paths before merging.
            for path in gmap:
                if path in file_map:
                    raise ValueError(
                        f"Duplicate render output path '{path}' produced by group "
                        f"'{selection_results[i].group_name}'. "
                        "Two classes resolved to the same output file — check class names and stereotypes."
                    )
            file_map.update(gmap)

        # Step 3 — emit scaffold if configured
        if self._config.include_scaffold:
            domain_groups = [
                {
                    "name": r.group_name,
                    "module_class": to_pascal_case(r.group_name) + "Module",
                }
                for r in selection_results
            ]
            scaffold_map = self._scaffold_emitter.render_scaffold(domain_groups)
            # DC3-04: scaffold keys must not clash with rendered class files.
            for path in scaffold_map:
                if path in file_map:
                    raise ValueError(
                        f"Scaffold output path '{path}' collides with a rendered class file. "
                        "This is a renderer bug — report it."
                    )
            file_map.update(scaffold_map)

        return file_map

    async def _render_group(
        self,
        result: SelectionResult,
        annotations: dict[str, object],
        node_map: dict[str, ClassNode],
        semaphore: asyncio.Semaphore,
    ) -> dict[PurePosixPath, bytes]:
        """Render all selected classes for one domain group."""
        file_map: dict[PurePosixPath, bytes] = {}

        for fqcn in result.selected:
            class_node = node_map.get(fqcn)
            if class_node is None:
                # Defensive: SelectionResult.selected uses the same IDs as the
                # graph, so this path should never be reached in normal operation.
                continue

            # DC3-03: isolate per-class render failures — one bad class must not
            # abort the rest of the group (D-008-2).
            try:
                async with semaphore:
                    rendered = await self._render_class(class_node, result.group_name, annotations)
            except Exception as exc:
                logger.warning(
                    "Failed to render class '%s' in group '%s': %s — skipping.",
                    fqcn,
                    result.group_name,
                    exc,
                )
                continue

            if rendered is not None:
                path, content = rendered
                # DC3-04: intra-group duplicate — two classes in the same domain
                # resolving to the same output path is always a bug, not a runtime error.
                if path in file_map:
                    raise ValueError(
                        f"Duplicate render output path '{path}' in group "
                        f"'{result.group_name}'. Two classes resolved to the same "
                        "output file — check class names and stereotypes."
                    )
                file_map[path] = content

        # Emit the domain module file for this group
        module_content = self._scaffold_emitter.render_domain_module(result, file_map)
        if module_content:
            module_path = PurePosixPath(f"src/{result.group_name}/{result.group_name}.module.ts")
            file_map[module_path] = module_content

        return file_map

    async def _render_class(
        self,
        class_node: ClassNode,
        group_name: str,
        annotations: dict[str, object],
    ) -> tuple[PurePosixPath, bytes] | None:
        """Dispatch one class through the feature-policy → LLM pipeline.

        Returns:
            ``(output_path, file_bytes)`` or ``None`` if the class is refused
            by a feature policy.
        """
        # --- Feature policies dispatch ---
        # DC3-05: dispatch_feature_policies returns a str refuse-reason when the class
        # is skipped, or a dict of render hints when it should proceed.
        hints = dispatch_feature_policies(class_node, annotations, self._config)
        if isinstance(hints, str):
            logger.debug(
                "Class '%s' refused by policy '%s' — skipping.",
                class_node.id,
                hints,
            )
            return None

        # --- Derive output path ---
        # The role suffix (.service.ts, .controller.ts, etc.) is derived from the
        # class stereotype so that _render_domain_module can classify files by
        # endswith() checks.  ADR-010 Fork 8 / Issue #1.
        simple_name = class_node.id.rsplit(".", 1)[-1]
        file_stem = to_kebab_case(simple_name)
        role_suffix = stereotype_to_role_suffix(class_node.stereotype)
        path = PurePosixPath(f"src/{group_name}/{file_stem}{role_suffix}")

        # --- LLM call ---
        content = await self._call_llm(class_node, annotations, hints)
        return path, content.encode("utf-8")

    async def _call_llm(
        self,
        class_node: ClassNode,
        annotations: dict[str, object],
        hints: dict[str, str],
    ) -> str:
        """Call the LLM render prompt for *class_node* and return TypeScript source.

        Loads ``prompts/render_file/v1.md`` from this package's own prompts
        directory, substitutes the required vars with ``render_prompt()``,
        and calls ``provider.complete_structured()`` in a thread pool so the
        async event loop is not blocked.

        **Precondition:** The prompt body must be written (M8) and the
        ``content_hash_pin`` must be updated by running
        ``scripts/update_prompt_hash_pins.py``.  Until then this method
        raises ``PromptLoadError``.

        Args:
            class_node:   The ClassNode to render.
            annotations:  Full annotations dict (fqcn → AnnotationRecord dict).
            hints:        Optional-var overrides injected by policy dispatch
                          (e.g. ``security_hint``, ``webflux_hint``).

        Returns:
            Raw TypeScript source as a string.
        """
        prompt = self._render_prompts.get("render_file", version="v1")

        annotation_data = annotations.get(class_node.id, {})

        # Build compact grounding summary passed as <<class_summary>>.
        # Gives the model upfront context before it parses the full JSON blobs,
        # reducing hallucination risk on class role and method count.
        _ann_raw = annotations.get(class_node.id)
        _methods: list[object] = []
        if isinstance(_ann_raw, dict):
            _inner = _ann_raw.get("annotation")
            if isinstance(_inner, dict):
                _methods_raw = _inner.get("methods")
                if isinstance(_methods_raw, list):
                    _methods = _methods_raw
        class_summary = "\n".join(
            [
                f"Resolved role: {class_node.stereotype or 'unknown'}",
                f"Class name: {class_node.name}",
                f"Top-level annotations: {', '.join(class_node.annotations or []) or 'none'}",
                f"Superclass: {class_node.superclass or 'null'}",
                f"Interfaces: {', '.join(class_node.implements or []) or 'null'}",
                f"Method count: {len(_methods)}",
            ]
        )

        user_text = render_prompt(
            prompt.user,
            fqcn=class_node.id,
            class_json=class_node.model_dump_json(),
            annotation_json=json.dumps(annotation_data),
            class_summary=class_summary,
            db_layer=self._config.db_layer,
            unsupported_feature_policy=self._config.unsupported_feature_policy,
            webflux_policy=self._config.webflux_policy,
            **hints,
        )
        messages: list[Message] = [
            Message(role="system", content=prompt.system, cache=CacheHint(ttl="1h")),
            Message(role="user", content=user_text),
        ]
        result = await asyncio.to_thread(
            lambda: self._provider.complete_structured(
                Tier.RENDER,
                messages,
                RenderedSource,
            )
        )
        return result.value.content

    # ------------------------------------------------------------------
    # Class selection + graph helpers
    # ------------------------------------------------------------------

    def _select_classes(self, graph: CodeographKnowledgeGraph) -> list[SelectionResult]:
        """Build a ClassSelector from config and run it over the graph."""
        grouping: DomainGrouping
        if self._config.domain_mapping:
            grouping = ManualMappingGrouping(self._config.domain_mapping)
        else:
            grouping = PackagePrefixGrouping()

        selector = ClassSelector(cap=self._config.render_budget, grouping=grouping)
        return selector.select(graph)

    def _build_node_map(self, graph: CodeographKnowledgeGraph) -> dict[str, ClassNode]:
        """Return a ``{fqcn: ClassNode}`` dict for the graph's class nodes."""
        from codeograph.graph.models.graph_schema import ClassNode as CN

        result: dict[str, ClassNode] = {}
        for node_wrapper in graph.nodes:
            node = node_wrapper.root
            if isinstance(node, CN):
                result[node.id] = node
        return result
