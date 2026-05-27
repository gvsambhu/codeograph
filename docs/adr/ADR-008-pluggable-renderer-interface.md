---
status: accepted
date: 2026-05-26
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-008 — Pluggable Renderer Interface

## Context and Problem Statement

The pipeline's terminal stage takes the assembled knowledge graph (AST data, complexity metrics, LLM-derived node annotations, corpus-level synthesis) and emits target-language source code. The legacy tool hard-wired this stage to a single TypeScript writer with a fixed interface (per-property metadata + `build_prompt` method + disk-direct write). Adding a second target (Go, Rust, Python-FastAPI, etc.) required edits in three places — the writer registry, the orchestrator's `__init__`, and the writer module import list.

This ADR defines the **pluggable contract** every target-language renderer must implement so additional targets can be added by dropping in a single package without modifying central code. The contract must serve four downstream consumers:
- the orchestrator (Pass 3 render step) that instantiates a renderer per the configured target
- the eval framework (separate ADR) that runs target-language compile checks on rendered output
- the cache + telemetry middleware (ADR-013/014/015) that wraps every LLM call the renderer makes
- the future snapshot-test layer (deferred) that compares rendered output byte-for-byte against golden artefacts

The contract must not leak target-specific knobs into central configuration, must not couple the eval layer to specific target tooling, and must keep the renderer focused on translation while reusing the shared cross-cutting middleware.

## Decision Drivers

* **SOLID-clean composition** — adding a renderer is a one-package change; central code is closed for modification
* **Forward compatibility with v1.1** — additive evolution path explicit (streaming render, sink-based output, manifest export of compile checks)
* **Tractable v1 implementation** — only the TypeScript/NestJS renderer ships in v1; the contract must be the minimum shape that supports a second target without rework
* **YAGNI** — don't pre-build for hypothetical S3 sinks, zip archives, dry-run callbacks, or stream consumers
* **Determinism / determinism boundary clarity** — LLM-rendered source files are non-deterministic; static scaffold files must be byte-stable to enable the future snapshot-test layer
* **No silent failures** — typos in renderer config sections fail at startup; unknown CLI targets fail before pipeline init; missing target tooling (`npx`, etc.) is reported, not crashed
* **Renderer ergonomics** — renderer authors write one config class, one renderer class, one templates directory, and one decorator-registered factory line
* **LLM budget preservation** — scaffold boilerplate (`package.json`, `tsconfig.json`, bootstrap files) generated via templates, not LLM calls

## Considered Options

### Fork 1 — Renderer return contract

* (a) disk-direct write — renderer accepts `output_dir` and writes files itself; returns a manifest of what was written.
* **(b) pure in-memory dict — renderer returns `dict[PurePosixPath, bytes]`; pipeline writes; additive `render_streaming()` method documented as future migration path. ✅**
* (c) generator yielding `RenderedFile` value objects.
* (d) sink abstraction — renderer pushes files into an injected `FileSink` (concrete `DirSink`, `InMemorySink`, future `S3Sink`).

### Fork 2 — Target-specific config ownership

* (a) renderer owns config schema; central `Settings` stores opaque `dict[str, dict[str, Any]]`; renderer factory validates on build.
* (b) central `Settings` has typed fields for every renderer (`Settings.renderers.typescript`, `Settings.renderers.go`).
* (c) CLI flags only; no config-file knobs for target-specific options.
* (d) dynamic `Settings` composition via `create_model` at import time.
* **(e) hybrid — renderer-owned config (`config_class` class attribute) + `Renderer[C]` generic for static enforcement + explicit `RendererRegistry` class with decorator-based registration + CLI guard validating target name and config-section keys against registry + `extra="forbid"` on every renderer config. ✅**

### Fork 3 — Eval hook contract

* (a) concrete method returning a command list — `compile_cmd() -> list[str]`.
* (b) central registry in the eval layer — `COMPILE_CHECKS: dict[str, list[str]]`.
* (c) sidecar manifest written into output — `.codeograph-meta.json` with check definitions.
* **(d) declarative method returning typed `CompileCheck` value objects — `compile_checks() -> list[CompileCheck]`; default `[]` opts the renderer out of eval. ✅**
* (e) static `ClassVar` list on the renderer class (no method).

### Fork 4 — Output scope

* (a) source files only — renderer emits translated classes; user provides project skeleton.
* (b) full skeleton, all LLM-generated — `package.json`, `tsconfig.json`, bootstrap and all source emitted via LLM calls.
* **(c) source files via LLM + scaffold via Jinja2 static templates committed in the renderer package; `include_scaffold: bool = True` opt-out in renderer config; reuses Jinja2 + `StrictUndefined` from ADR-014. ✅**
* (d) mode flag (`Literal["source_only", "full_project"]`) with implementation hidden behind it.

### Fork 5 — LLM call ownership

* **(a) renderer takes a stacked `LlmProvider` via constructor injection; owns its LLM calls; constructor parameter order mirrors prior pass orchestrators (`config, provider, prompt_loader, concurrency`); cross-cutting concerns (retry, caching, telemetry) delegated to the middleware stack. ✅**
* (b) renderer returns prompt plans; pipeline executes; renderer assembles results (plan/execute/assemble two-phase API).
* (c) hybrid — renderer owns simple calls; pipeline-mediated `RenderContext` helper for complex orchestration.
* (d) renderer takes a `RenderContext` value object holding provider + auxiliaries.

## Decision Outcome

### Fork 1 — Renderer return contract: (b) pure in-memory dict

The renderer base class declares a single abstract `render()` method returning `dict[PurePosixPath, bytes]`. The pipeline owns disk I/O. The renderer remains a pure transformation from `(graph, annotations) -> file map` and stays decoupled from output destination.

```python
# codeograph/renderers/base.py
from abc import ABC, abstractmethod
from pathlib import PurePosixPath

class Renderer(ABC, Generic[C]):
    @abstractmethod
    def render(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: LlmAnnotations,
    ) -> dict[PurePosixPath, bytes]:
        """Return {relative_path: file_bytes}. Caller writes to disk."""
```

**Migration plan for streaming (documented, not implemented):** when a renderer's projected output exceeds ~100 MB total OR when per-file progress UX requires more than a callback hook, add a non-abstract `render_streaming(...) -> Iterator[RenderedFile]` method to the ABC. Default implementation collects the dict and yields entries; streaming-native renderers override `render_streaming` and implement `render` as a thin collector. Migration is purely additive — existing renderers and consumers do not change. Trigger conditions stay documented in this ADR so a future contributor does not re-litigate the option.

**v1 output volume bound:** with ADR-009's default cap of 3 classes per domain, a 50-domain corpus renders ~150 TS files at ~5 KB each — under 1 MB total. Memory cost is irrelevant at this scale.

### Fork 2 — Target-specific config: (e) hybrid

Each renderer declares its own Pydantic config class, advertises it via a `config_class` class attribute, and parameterizes the `Renderer` base via `Generic[C]` so static type checkers enforce that the constructor argument type matches the declared `config_class`. An explicit `RendererRegistry` class holds the target-name → renderer-class mapping; registration happens at module import time via `@RendererRegistry.register("<target>")` decorator. Central `Settings` stores `renderers: dict[str, dict[str, Any]]` (opaque). At CLI startup, the orchestrator validates that the `--target` value is in the registry AND that every key under `settings.renderers` is a known target — typos fail before pipeline init. Each renderer config uses `model_config = ConfigDict(extra="forbid")` so unknown keys inside a renderer's section also fail loudly.

```python
# codeograph/renderers/base.py
from typing import ClassVar, Generic, TypeVar
from pydantic import BaseModel

C = TypeVar("C", bound=BaseModel)

class Renderer(ABC, Generic[C]):
    config_class: ClassVar[type[BaseModel]]   # advertised; checked at registration

    @abstractmethod
    def __init__(
        self,
        config: C,
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        concurrency: int = 5,
    ) -> None: ...
```

```python
# codeograph/renderers/registry.py
class RendererRegistry:
    _items: ClassVar[dict[str, type[Renderer]]] = {}

    @classmethod
    def register(cls, target: str):
        def decorator(renderer_cls: type[Renderer]) -> type[Renderer]:
            if not hasattr(renderer_cls, "config_class"):
                raise TypeError(
                    f"{renderer_cls.__name__} must define `config_class`"
                )
            if target in cls._items:
                raise ValueError(f"Target {target!r} already registered")
            cls._items[target] = renderer_cls
            return renderer_cls
        return decorator

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._items)

    @classmethod
    def build(
        cls,
        target: str,
        raw_config: dict[str, Any],
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        concurrency: int = 5,
    ) -> Renderer:
        if target not in cls._items:
            raise ValueError(
                f"Unknown target {target!r}. Available: {cls.available()}"
            )
        renderer_cls = cls._items[target]
        config = renderer_cls.config_class.model_validate(raw_config)
        return renderer_cls(
            config=config,
            provider=provider,
            prompt_loader=prompt_loader,
            concurrency=concurrency,
        )
```

```python
# codeograph/renderers/typescript_nestjs/renderer.py
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
```

The decorator-based registration makes the registry and the renderer module the same source of truth — there is no separate import list to keep in sync.

### Fork 3 — Eval hook contract: (d) declarative `compile_checks()`

The base class declares a non-abstract `compile_checks() -> list[CompileCheck]` method returning a list of typed value objects. Default implementation returns `[]` so renderers can opt out of eval (e.g., experimental renderers). Each `CompileCheck` describes one verification command, the tools it requires (so the eval framework can preflight via `shutil.which` and skip-with-message rather than crash), the working directory, and the exit codes that count as a pass.

```python
# codeograph/renderers/base.py
from dataclasses import dataclass

@dataclass(frozen=True)
class CompileCheck:
    name: str
    cmd: tuple[str, ...]
    workdir: PurePosixPath = PurePosixPath(".")
    required_tools: tuple[str, ...] = ()
    pass_on_exit_codes: tuple[int, ...] = (0,)


class Renderer(ABC, Generic[C]):
    # ... __init__, render ...

    def compile_checks(self) -> list[CompileCheck]:
        """Default: no checks (renderer opts out of eval).
        Override to declare one or more checks."""
        return []
```

```python
# codeograph/renderers/typescript_nestjs/renderer.py
def compile_checks(self) -> list[CompileCheck]:
    cmd = ["npx", "tsc", "--noEmit"]
    if self._config.strict:
        cmd.append("--strict")
    return [CompileCheck(
        name="tsc",
        cmd=tuple(cmd),
        required_tools=("npx",),
    )]
```

The eval framework iterates `renderer.compile_checks()`, preflights `required_tools`, runs each command with `subprocess.run`, and records pass/skip/fail in the scorecard.

**Manifest export deferred.** Adding the resolved check list to the run manifest (so external CI can replay the exact command without invoking Codeograph) is a non-breaking schema bump that can be added later. No v1 consumer exists; the natural trigger is the future eval framework ADR or the future snapshot-test ADR. Deferring avoids committing to a manifest field shape (flat vs nested under `artefacts`) before a real consumer informs the decision.

### Fork 4 — Output scope: (c) source via LLM + Jinja2 scaffold templates

The renderer emits two classes of files in the same return dict:
1. **Translated source files** — produced via LLM calls (per-class granularity; see ADR-010).
2. **Scaffold files** — produced via Jinja2 templates committed in the renderer's `templates/` directory, rendered with corpus metadata (project name, detected modules, etc.) using the same `StrictUndefined` engine ADR-014 established for prompts.

A `include_scaffold: bool = True` field on the renderer config provides the opt-out for users integrating output into an existing project. With `include_scaffold: false`, only the LLM-generated source files appear in the output dict.

```
codeograph/renderers/typescript_nestjs/
├── __init__.py
├── renderer.py
├── config.py
├── prompts/
│   └── render_file/                   # LLM prompts (ADR-014 layout)
│       └── v1.md
└── templates/                         # Jinja2 scaffold templates
    ├── package.json.j2
    ├── tsconfig.json.j2
    ├── nest-cli.json.j2
    ├── .gitignore.j2
    └── src/
        ├── main.ts.j2
        └── app.module.ts.j2
```

The split assigns LLM work to translation (where only an LLM can perform the work) and Jinja2 to boilerplate (where determinism and zero LLM cost both matter). Scaffold byte-stability satisfies the future snapshot-test layer; LLM output is excluded from byte-stability requirements per ADR-007.

**Preflight check:** at render start, validate that every `.j2` template renders without `UndefinedError` against the current corpus metadata. A template referencing `{{ project_description }}` that corpus did not populate fails at render time, not at `npm install`.

### Fork 5 — LLM call ownership: (a) renderer-owned via constructor DI

The renderer's constructor accepts an `LlmProvider` instance via dependency injection — the same shape the Pass 1 (node-annotation) and Pass 2 (corpus-synthesis) orchestrators already use. The provider is pre-stacked with the standard middleware (Telemetry → Caching → Retry → Provider) per ADR-013. Inside `render()`, the renderer constructs prompts, calls `self._provider.complete_structured(...)`, parses responses, and assembles the file map. Concurrency is bounded by the constructor's `concurrency` parameter (default 5, matching ADR-005's locked concurrency).

This keeps the three LLM-using passes (annotation, synthesis, render) on the same construction shape so consumers and tests use one mental model:

```python
# All three passes follow the same DI shape:
annotator   = NodeAnnotator(provider, prompt_loader, out_dir, concurrency=5)
synthesizer = CorpusSynthesizer(provider, prompt_loader, out_dir)
renderer    = TypeScriptRenderer(config, provider, prompt_loader, concurrency=5)
```

Cross-cutting concerns (retry, caching, telemetry, cost attribution) are handled "for free" by the stacked provider; the renderer's only LLM-related code is the `self._provider.complete_structured(...)` call. Render-time `CallContext` carries `Purpose.RENDER` + `Tier.RENDER` enums already shipped in ADR-013.

**Constructor parameter order is locked** as `(config, provider, prompt_loader, concurrency)` so anyone reading `TypeScriptRenderer(...)` recognizes the pattern from `NodeAnnotator(...)`.

### Constraint flagged for ADR-009

ADR-009 (Rendering Budget Cap) decides which classes get fed to the renderer. The renderer takes a fully-prepared `(graph, annotations)` pair and translates whatever it is given — selection is not a renderer concern. ADR-009 must therefore produce a filtered subgraph (or a selection result the orchestrator applies before invoking the renderer) so the renderer signature does not need a separate `cap` parameter.

### Constraint flagged for ADR-010

ADR-010 (Spring → TS/NestJS Mapping) populates the concrete `TypeScriptConfig` field set, the `templates/` directory contents, and the per-class LLM prompt under `prompts/render_file/v1.md`. The `Renderer[C]` generic parameter binds to `TypeScriptConfig`; the `config_class` class attribute references it; the scaffold templates honor the `include_scaffold` and `strict` fields and any additional knobs ADR-010 introduces.

### Constraint flagged for future Go renderer

The same shape applies when a Go renderer is added: one new package under `codeograph/renderers/go_<framework>/`, one new config class, one `templates/` directory with `go.mod.j2` / `main.go.j2`, and one `@RendererRegistry.register("go")` decorator. No edit to `Settings`, no edit to the orchestrator, no edit to the CLI's target validation (it reads from `RendererRegistry.available()`).

## Consequences

**Positive.**
1. Adding a target language is a one-package change — `Settings`, the orchestrator, and the eval framework all stay closed for modification.
2. Mypy/pyright statically enforce that `config_class` matches the constructor argument type via the `Generic[C]` parameter — a class of bug becomes a type error.
3. CLI startup catches typos in `--target` values and config section names before pipeline init runs.
4. Scaffold byte-stability satisfies the future snapshot-test layer; LLM-rendered files are correctly excluded from byte-stability requirements per ADR-007.
5. The renderer reuses the entire ADR-013/014/015 middleware stack — retry, caching, telemetry, and cost attribution work without renderer-side code.
6. The `templates/` pattern establishes a precedent for future renderers — scaffolds are committed Jinja2 artefacts, reviewable in pull requests as readable diffs.

**Negative.**
1. Five primary forks plus a dataclass (`CompileCheck`) and a registry class (`RendererRegistry`) mean the renderer subsystem is more structured than a single-file writer — a contributor adding a target reads more code before producing their first commit.
2. The dict-return shape buffers the whole output in memory. v1 worst-case (~1 MB) is trivial, but a future high-volume target (10k-file corpus) will need the streaming migration.
3. Configuration validation happens at the renderer-factory boundary, not at `Settings` load time — a typo under `renderers.tipescript:` is harmless until the user requests that target. The CLI guard mitigates this for the common case (validating section keys against the registry) but the residual gap exists.
4. `Renderer[C]` requires a `TypeVar` and a `ClassVar` declaration that some contributors will find unfamiliar; the generic parameter is the cost of static enforcement.

## Confirmation

1. `RendererRegistry.available()` returns at least `["typescript"]` immediately after `codeograph.renderers.typescript_nestjs` is imported, with no extra import-list maintenance needed.
2. Attempting to register a `Renderer` subclass without a `config_class` class attribute raises `TypeError` at decoration time (verified by unit test).
3. Attempting to register a target name already in the registry raises `ValueError` (verified by unit test).
4. Running the CLI with an unknown `--target` value (e.g., `--target rust`) fails at startup with a message listing available targets; pipeline init does not run.
5. Running the CLI with a config file containing an unknown top-level renderer section (e.g., `renderers.tipescript:`) fails at startup with a message listing known target names.
6. Running the CLI with a config file containing an unknown field inside a known renderer section (e.g., `renderers.typescript.haetoas_mode: self`) fails at startup with a Pydantic `extra_forbidden` error pointing at the bad key.
7. A `TypeScriptRenderer` instance returns at least one `CompileCheck` from `compile_checks()`; that check has `required_tools=("npx",)` so the eval framework's preflight has something to verify.
8. Rendering a small corpus with `include_scaffold: true` produces a `package.json`, `tsconfig.json`, and `src/main.ts` in the output dict alongside the translated source files; with `include_scaffold: false` only translated source appears.
9. Mypy/pyright reject a hypothetical `class BadRenderer(Renderer[TypeScriptConfig])` whose `__init__` accepts a `GoConfig` parameter (verified by a type-error fixture).
10. A `MockLlmProvider` injected into `TypeScriptRenderer` causes the rendered output to match the mock's prepared responses byte-for-byte, with zero network calls (verified by unit test).

## Pros and Cons of the Considered Options

### Fork 1 — Renderer return contract

**(a) disk-direct write.**
* Good, because memory cost stays constant regardless of output size.
* Good, because renderer authors have a simpler signature with no path-key invariants to maintain.
* Bad, because every renderer must reimplement output-path safety and `--force` handling — security duplication is the worst kind.
* Bad, because unit tests need `tmp_path` fixtures and post-write directory walks instead of dict equality.
* Bad, because the renderer is coupled to a writable filesystem, blocking dry-run and future in-memory consumers.

**(b) pure in-memory dict. ✅ Chosen.**
* Good, because I/O concentration matches project posture — `--force` and future output-path safety belong in the pipeline, not in every renderer.
* Good, because unit tests reduce to dict equality with no temp directories.
* Good, because the future snapshot-test layer compares dicts naturally — no filesystem walk, no path normalization quirks across OSes.
* Good, because future in-memory or S3 consumers work without renderer changes.
* Bad, because the whole output is held in memory before write; trivial at v1 scale but real at very high volumes.
* Bad, because progress UX requires a separate callback hook rather than a natural per-file boundary.

**(c) generator yielding `RenderedFile`.**
* Good, because peak memory is one file at a time.
* Good, because per-file progress is natural at the `yield` boundary.
* Bad, because aggregate operations (e.g., emitting a manifest listing all written files) require a second pass or buffering.
* Bad, because mid-stream failures leave partial output unless a transactional write protocol is added.
* Neutral, because tests can drain the iterator, but it is more friction than dict equality.

**(d) sink abstraction with `InMemorySink` default.**
* Good, because future extensibility (S3, zip, dry-run) is built in.
* Bad, because two abstractions on day one (renderer + sink) increase cognitive load for renderer authors with no concrete v1 consumer.
* Bad, because the renderer becomes side-effect-only and can't return rich metadata without bolting a return type back on.
* Bad, because YAGNI — no S3 or zip-archive sink is on the roadmap.

### Fork 2 — Target-specific config ownership

**(a) renderer owns config, opaque central dict.**
* Good, because adding a renderer is a one-package change.
* Good, because validation still happens at startup via the factory's `model_validate(raw)`.
* Bad, because nothing statically enforces that the declared `config_class` matches the `__init__` argument type.
* Bad, because top-level typos under `renderers:` are silently kept until something requests the misspelled target.

**(b) typed central sections in `Settings`.**
* Good, because end-to-end IDE autocomplete works across the codebase.
* Good, because unknown sections fail immediately at `Settings` load.
* Bad, because central `Settings` grows with every renderer — violates one-file-extensibility.
* Bad, because mild circular-import risk between `Settings` and renderer configs.

**(c) CLI flags only.**
* Good, because explicit at invocation — readable in CI logs.
* Bad, because the CLI surface explodes — N targets × M flags per target.
* Bad, because project-level preferences cannot be expressed; users re-type the same flags every run.
* Bad, because adding a renderer requires Click changes to the CLI module.

**(d) dynamic `Settings` composition.**
* Good, because central composition coexists with one-file extensibility in theory.
* Bad, because pyright/mypy cannot see the dynamically composed model — IDE autocomplete fails.
* Bad, because import-order fragility — `Settings` must be imported after every renderer registers itself.
* Bad, because test isolation is harder — registry state leaks across tests.

**(e) hybrid (generic + explicit registry + CLI guard + extra=forbid). ✅ Chosen.**
* Good, because it preserves one-file-extensibility — `Settings` stays lean.
* Good, because the `Renderer[C]` generic parameter makes the config/constructor type match statically enforceable.
* Good, because the decorator-based registry makes the registry and the renderer module the same source of truth.
* Good, because `extra="forbid"` plus the CLI section-key validator close the top-level typo gap that pure renderer-owned config leaves open.
* Bad, because contributors must understand four pieces (config class + `Renderer[C]` generic + registry decorator + CLI guard) instead of one Pydantic field.

### Fork 3 — Eval hook contract

**(a) concrete `compile_cmd()` returning a list.**
* Good, because it is trivially simple — one method, one return type.
* Bad, because only a single check can be expressed; TS + ESLint cannot coexist.
* Bad, because no metadata — no name for logs, no preflight, no workdir flexibility.
* Bad, because the return is stringly typed — opaque to the type system.

**(b) central registry in the eval layer.**
* Good, because the eval layer is fully decoupled from renderer code.
* Bad, because it creates two sources of truth — adding a renderer means editing the renderer package AND the eval registry.
* Bad, because the registry has no access to renderer config; per-instance variations (`--strict`) cannot influence the command.
* Bad, because it violates OCP — adding a renderer modifies the eval module.

**(c) sidecar manifest file in output.**
* Good, because it is fully decoupled — eval imports nothing from renderers.
* Good, because external tools could consume the manifest without invoking Codeograph.
* Bad, because it adds a non-source-code file to the rendered output, polluting the project.
* Bad, because the writer/reader schema can drift silently.

**(d) declarative method returning typed `CompileCheck` value objects. ✅ Chosen.**
* Good, because multiple checks are first-class (a list).
* Good, because the renderer's instance config flows into the command naturally — `--strict` toggles the cmd.
* Good, because `required_tools` enables preflight via `shutil.which`, turning crashes into recorded skips.
* Good, because the method/value-object shape is a sibling to Fork 2's declarative `config_class` pattern — one mental model for renderer metadata.
* Bad, because it is slightly heavier than option (a) — one dataclass plus one method.

**(e) static `ClassVar` list.**
* Good, because it is fully declarative — pure data, no behavior.
* Bad, because it cannot read instance config — the TS `--strict` toggle in `TypeScriptConfig` cannot influence the command.
* Bad, because two renderer instances with different configs share the same checks — wrong semantics.

### Fork 4 — Output scope

**(a) source files only.**
* Good, because the renderer scope stays minimal.
* Good, because it is a clean drop-in for users with an existing NestJS project.
* Bad, because the output is not runnable without a hand-written project skeleton.
* Bad, because the `compile_checks()` contract from Fork 3 needs `tsconfig.json` to exist somewhere; ad-hoc CLI flags do not match real-world usage.
* Bad, because it perpetuates the legacy gap of users hand-wiring module files.

**(b) full skeleton, all LLM-generated.**
* Good, because the codepath is maximally consistent — every file flows through `prompt → LLM → file`.
* Bad, because it wastes LLM cost on boilerplate (`tsconfig.json` is the same on every run).
* Bad, because scaffold output is non-deterministic — LLM variance breaks the future snapshot-test layer.
* Bad, because critical files (`package.json`) face hallucination risk on dependency versions.

**(c) source via LLM + Jinja2 scaffold templates, opt-out via config. ✅ Chosen.**
* Good, because output is immediately runnable by default — `npm install && npm run start:dev` works.
* Good, because the scaffold portion is deterministic — Jinja2 over committed templates produces byte-stable output.
* Good, because no LLM cost on boilerplate.
* Good, because `include_scaffold: false` provides a clean opt-out for integration scenarios.
* Good, because templates are pull-request reviewable as readable diffs.
* Bad, because two rendering codepaths live inside the renderer (LLM for source, Jinja2 for scaffold), increasing the renderer's surface area.

**(d) mode flag with implementation hidden behind it.**
* Good, because it is maximally flexible at the contract level.
* Bad, because it does not actually decide the design question — punts the `how` to each renderer.
* Bad, because two test paths per renderer must exist (both modes need coverage).
* Bad, because default `full_project` still needs Option (b) or (c) internally; "configurable" without prescribing the mechanism is not a real decision.

### Fork 5 — LLM call ownership

**(a) renderer-owned via constructor DI. ✅ Chosen.**
* Good, because it matches the construction shape Pass 1 and Pass 2 orchestrators already use — one mental model across all three LLM-using passes.
* Good, because all cross-cutting concerns (retry, caching, telemetry) are handled by the pre-stacked provider — the renderer's only LLM-related code is a single `complete_structured(...)` call.
* Good, because per-file progress and mid-render dependency lookups are naturally possible within the render loop.
* Good, because tests inject `MockLlmProvider` — same harness as Pass 1 and Pass 2.
* Bad, because the constructor takes four parameters rather than one.

**(b) plan/execute/assemble two-phase API.**
* Good, because the renderer is pure — `plan()` and `assemble()` are unit-testable without mocks.
* Good, because the pipeline owns concurrency centrally.
* Bad, because it introduces a third construction pattern alien to Pass 1 and Pass 2 — fragments the codebase.
* Bad, because mid-render decisions (controller translation referencing already-translated service) cannot loop back.
* Bad, because per-file progress cannot fire until `assemble()` runs after all LLM calls complete.

**(c) hybrid with `RenderContext` helper.**
* Good, because it is maximally flexible.
* Bad, because two ways to make the same call create inconsistent renderers.
* Bad, because renderer authors face an unclear decision point ("should I use the helper or call directly?").
* Bad, because it punts the actual design question.

**(d) `RenderContext` value object holding provider + auxiliaries.**
* Good, because the constructor signature is cleaner (two parameters, not four).
* Good, because future extensibility — adding fields does not change every renderer signature.
* Bad, because it carries god-bag risk — `RenderContext` would start at four fields and grow over time.
* Bad, because it is inconsistent with Pass 1 and Pass 2 which take provider directly.

## More Information

### Relationships

* **ADR-001** (project skeleton & config) — pydantic-settings priority chain (init kwargs > env > .env > yaml > defaults) flows through `Settings.renderers` to renderer-owned configs via the standard nested-delimiter mechanism.
* **ADR-005** (token utilization) — `Tier.RENDER` resolves to the same Sonnet model used by Pass 1 and Pass 2; no top-tier escalation in v1.
* **ADR-006** (knowledge graph schema) — renderer consumes the two-file output (`graph.json` + `llm-annotations.json`) joined at render time by id.
* **ADR-007** (golden-graph pattern) — renderer output is explicitly NOT in the golden contract; the future snapshot-test layer handles renderer byte-stability for the scaffold portion only.
* **ADR-009** (rendering budget cap) — `ClassSelector` produces the filtered subgraph the renderer receives; renderer does not implement selection.
* **ADR-010** (Spring → TS/NestJS mapping) — populates `TypeScriptConfig`, the `templates/` contents, and the per-class render prompt.
* **ADR-013** (LLM provider abstraction) — `LlmProvider` middleware stack handles retry, caching, telemetry; renderer injects the stacked provider without knowing the layers.
* **ADR-014** (prompt versioning) — `render_file/v1.md` prompt lives under `codeograph/renderers/typescript_nestjs/prompts/`; reuses the `StrictUndefined` Jinja2 engine for both prompts and scaffold templates.
* **ADR-015** (telemetry + response cache) — `rendered_input_hash` is part of the cache key; per-class render granularity (ADR-010 Fork 8) maximizes cache reuse.

### Deferred items

* **Streaming render** — `render_streaming(...) -> Iterator[RenderedFile]` method, added when projected output exceeds ~100 MB OR when partial-failure recovery is needed. Migration path is purely additive; existing renderers do not change.
* **Manifest export of `compile_checks`** — adds the resolved check list to `manifest.json` so external CI can replay verification without invoking Codeograph. Trigger: when the eval framework ADR or future snapshot-test ADR has a concrete consumer informing the field shape (flat vs nested under `artefacts`).
* **Sink-based output abstraction** — only if a concrete S3, zip-archive, or external sink consumer materializes; the dict return shape can wrap into a sink at the pipeline boundary without renderer changes.

### Open Questions / Future Work

* Did the `Renderer[C]` generic parameter catch real bugs that opaque `Renderer` would not have? Review after DC3 ships.
* Did `RendererRegistry` stay a focused class or accumulate orchestration responsibilities? Watch for god-class drift.
* Did `include_scaffold: false` see real use, or did every consumer want the full scaffold? Inform v1.1 default.
* Did the `CompileCheck.required_tools` preflight prevent crashes on machines without target tooling installed?
* Did the dict-return memory profile match expectations (<100 MB) on the largest evaluated corpus? Inform the streaming migration trigger.

### References

* Lanza & Marinescu (2006). *Object-Oriented Metrics in Practice* — referenced indirectly via ADR-009's class-selection thresholds, which the renderer consumes through the filtered subgraph.
* NestJS Documentation — Modules and Providers. https://docs.nestjs.com/modules
* Pydantic v2 — `model_config = ConfigDict(extra="forbid")` for strict schema validation. https://docs.pydantic.dev/latest/concepts/models/#extra-fields
