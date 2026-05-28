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
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import BaseModel

from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render as render_prompt
from codeograph.llm.types import CacheHint, Message, Tier
from codeograph.renderers.base import CompileCheck, Renderer
from codeograph.renderers.registry import RendererRegistry
from codeograph.renderers.typescript_nestjs.config import TypeScriptConfig
from codeograph.rendering.class_selector import ClassSelector, SelectionResult
from codeograph.rendering.domain_grouping import (
    DomainGrouping,
    ManualMappingGrouping,
    PackagePrefixGrouping,
)

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import ClassNode, CodeographKnowledgeGraph
    from codeograph.llm.provider import LlmProvider

__all__ = ["TypeScriptRenderer"]

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Package name for Jinja2 PackageLoader (resolved relative to this file's package)
_TEMPLATE_PACKAGE = "codeograph.renderers.typescript_nestjs"
_TEMPLATE_DIR = "templates/scaffold"

# NestJS version pinned per Q1 decision
_NESTJS_VERSION = "^10.4.0"
_TYPEORM_VERSION = "^0.3.20"
_PG_VERSION = "^8.12.0"
_BETTER_SQLITE3_VERSION = "^9.6.0"

# Spring Security annotation simple names that trigger security_feature_policy.
# Source: Spring Security 6 reference, §Method Security and §Web Security.
_SPRING_SECURITY_ANNOTATIONS: frozenset[str] = frozenset(
    {
        "PreAuthorize",
        "PostAuthorize",
        "Secured",
        "RolesAllowed",
        "PreFilter",
        "PostFilter",
        "EnableWebSecurity",
        "EnableMethodSecurity",
        "WithMockUser",  # test annotations — also trigger the policy
    }
)


# ---------------------------------------------------------------------------
# Pydantic wrapper for code-gen LLM output
# ---------------------------------------------------------------------------


class RenderedSource(BaseModel):
    """Single-field wrapper used with ``complete_structured()`` for code-gen output.

    The render prompt instructs the model to return its TypeScript source code
    in the ``content`` field.  Using ``complete_structured()`` keeps the
    provider abstraction intact — no raw-text completion method is needed.
    The model must JSON-escape the TypeScript content; Pydantic validates it.
    """

    content: str


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

        # Jinja2 environment — StrictUndefined catches template typos at render
        # time rather than silently emitting empty strings (same policy as ADR-014).
        self._jinja: Environment = Environment(
            loader=PackageLoader(_TEMPLATE_PACKAGE, _TEMPLATE_DIR),
            undefined=StrictUndefined,
            autoescape=False,
        )

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
        group_maps: list[dict[PurePosixPath, bytes]] = await asyncio.gather(*render_tasks)

        for gmap in group_maps:
            file_map.update(gmap)

        # Step 3 — emit scaffold if configured
        if self._config.include_scaffold:
            domain_groups = [
                {
                    "name": r.group_name,
                    "module_class": _to_pascal_case(r.group_name) + "Module",
                }
                for r in selection_results
            ]
            scaffold_map = self._render_scaffold(domain_groups)
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

            async with semaphore:
                rendered = await self._render_class(class_node, result.group_name, annotations)

            if rendered is not None:
                path, content = rendered
                file_map[path] = content

        # Emit the domain module file for this group
        module_content = self._render_domain_module(result, file_map)
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
        hints: dict[str, str] = {}

        # --- Spring Security policy (deterministic from ClassNode.annotations) ---
        # ClassNode.annotations is the list of ALL annotation simple names on
        # the class (e.g. ["RestController", "PreAuthorize", "Validated"]).
        class_annotations: set[str] = set(class_node.annotations or [])
        security_hits = _SPRING_SECURITY_ANNOTATIONS & class_annotations
        if security_hits:
            if self._config.security_feature_policy == "exclude":
                return None
            # "stub_with_todo": inject a hint so the model emits a Guard stub.
            hints["security_hint"] = (
                f"This class carries Spring Security annotation(s): "
                f"{', '.join(sorted(security_hits))}. "
                f"Emit a NestJS @UseGuards() decorator stub with a "
                f"// TODO(learner): replace with a real Guard implementation."
            )

        # --- WebFlux policy (from Pass 1 method return types) ---
        # TODO(learner): detect WebFlux reactive types and apply webflux_policy.
        #
        # The annotations dict maps fqcn → AnnotationRecord dict (the JSON-decoded
        # form of llm-annotations.json).  Each record has this structure:
        #
        #   {
        #     "node_id": "com.example.orders.OrderService",
        #     "degraded": false,
        #     "annotation": {
        #       "methods": [
        #         {"name": "findAll", "return_type": "Flux<OrderDto>", ...},
        #         ...
        #       ]
        #     }
        #   }
        #
        # Detection recipe:
        #   record = annotations.get(class_node.id)
        #   if isinstance(record, dict):
        #       ann = record.get("annotation") or {}
        #       methods = ann.get("methods", []) if isinstance(ann, dict) else []
        #       uses_webflux = any(
        #           "Mono<" in m.get("return_type", "") or
        #           "Flux<" in m.get("return_type", "")
        #           for m in methods
        #           if isinstance(m, dict)
        #       )
        #       if uses_webflux:
        #           if self._config.webflux_policy == "refuse_to_render":
        #               return None
        #           hints["webflux_hint"] = (
        #               "This class uses Spring WebFlux reactive types "
        #               "(Mono<T>/Flux<T>). Emit Promise<T>/AsyncIterable<T> "
        #               "equivalents with a // TODO(learner): comment."
        #           )

        # --- Derive output path ---
        simple_name = class_node.id.rsplit(".", 1)[-1]
        file_stem = _to_kebab_case(simple_name)
        path = PurePosixPath(f"src/{group_name}/{file_stem}.ts")

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
    # Scaffold emission
    # ------------------------------------------------------------------

    def _render_scaffold(self, domain_groups: list[dict[str, str]]) -> dict[PurePosixPath, bytes]:
        """Emit the NestJS project skeleton using Jinja2 scaffold templates."""
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

    def _render_domain_module(
        self,
        result: SelectionResult,
        group_file_map: dict[PurePosixPath, bytes],
    ) -> bytes | None:
        """Emit a NestJS module barrel for *result.group_name*.

        TODO(learner): implement this method.

        Steps:
            1. Classify the files in ``group_file_map`` by filename suffix:
                 Controllers : path.name ends with ``.controller.ts``
                 Services    : path.name ends with ``.service.ts``
                 Entities    : path.name ends with ``.entity.ts``
                 Repositories: path.name ends with ``.repository.ts``
               For each file, derive the class name from the file stem:
                 ``order-service.ts``  → stem ``order-service``
                 class name ``OrderService`` (pascal-case the stem)
            2. Build the Jinja2 template context::
                 {
                   "group_name": result.group_name,
                   "module_class_name": _to_pascal_case(result.group_name) + "Module",
                   "selected_count": result.total_in_group,
                   "selection_strategy": result.strategy,
                   "controllers": [{"class_name": ..., "file_stem": ...}, ...],
                   "services": [...],
                   "entities": [...],
                   "repositories": [...],
                 }
            3. Render ``domain.module.ts.j2`` via ``self._emit_template()``.
            4. Return the rendered bytes.

        Reference: ``templates/scaffold/domain.module.ts.j2`` for the expected
        context keys.
        """
        controllers = []
        services = []
        entities = []
        repositories = []

        for path in group_file_map.keys():
            if path.name.endswith(".controller.ts"):
                controllers.append({"class_name": _to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".service.ts"):
                services.append({"class_name": _to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".entity.ts"):
                entities.append({"class_name": _to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem})
            elif path.name.endswith(".repository.ts"):
                repositories.append(
                    {"class_name": _to_pascal_case(path.stem.replace("-", "_")), "file_stem": path.stem}
                )

        context: dict[str, object] = {
            "group_name": result.group_name,
            "module_class_name": _to_pascal_case(result.group_name) + "Module",
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


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _to_pascal_case(name: str) -> str:
    """``"orders"`` → ``"Orders"``, ``"order-items"`` → ``"OrderItems"``."""
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_"))


def _to_kebab_case(name: str) -> str:
    """``"OrderService"`` → ``"order-service"``."""
    import re

    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s1)
    return s2.lower()


def _db_adapter_info(adapter: str) -> tuple[str, str]:
    """Return ``(npm_package_name, version_constraint)`` for *adapter*."""
    if adapter == "pg":
        return "pg", _PG_VERSION
    if adapter == "better-sqlite3":
        return "better-sqlite3", _BETTER_SQLITE3_VERSION
    raise ValueError(f"Unknown db_adapter: {adapter!r}")
