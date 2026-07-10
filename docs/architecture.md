# Architecture — current snapshot (v1 / DC1–DC5)

This page describes what is implemented **today**. It is updated as each delivery chunk (DC) lands. The decision flow that led here lives in [`docs/adr/`](adr/); this page is the snapshot.

## What each DC delivered

| DC | Deliverable |
|---|---|
| DC1 | Deterministic AST pipeline → `graph.json` + initial `manifest.json` |
| DC2 | LLM enrichment passes (Pass 1 annotator, Pass 2 synthesizer) → `llm-annotations.json`; response cache; telemetry JSONL |
| DC3 | TypeScript/NestJS renderer; pluggable renderer registry (ADR-008/010) |
| DC4 | Eval framework — scorecards, compile checks, golden-graph regression (ADR-017/018) |
| DC5 | Run manifest v2.0.0 (ADR-025 flat layout); structured logging (JSONL + plaintext); gitleaks secret scanning (ADR-022/023) |

## DC1 — Deterministic graph pipeline

### Pipeline

```
INPUT  →  ACQUIRE  →  DISCOVER  →  PARSE  →  BUILD  →  ASSEMBLE  →  WRITE  →  OUTPUT
 path/         CorpusSpec      ParsedFile     fragment       merged graph     graph.json
 git url/                                     per file
 zip
```

The manifest is NOT written by this pipeline. Per the ADR-025 write-protocol amendment, the manifest appears only at a terminal write orchestrated by the `codeograph run` command.

Each box is a focused class. CLI wires them together (`codeograph/cli/main.py`).

| Stage | Component | Output | ADR |
|---|---|---|---|
| Acquire | `InputAcquirer` + `acquirers/{local,git,zip}` | `CorpusSpec` on local FS | [ADR-002](adr/ADR-002-input-agnostic-design.md) |
| Discover | `SourceDiscoverer` | `ModuleSpec[]` with `java_files[]` | [ADR-002](adr/ADR-002-input-agnostic-design.md) |
| Parse | `FileParserDispatcher` → `JavaFileParser` (JAR subprocess) → `RegexFallback` | `ParsedFile` envelope (TypedDict) | [ADR-003](adr/ADR-003-parsing-strategy.md) |
| Build | `GraphBuilder` | per-file graph fragment | [ADR-006](adr/ADR-006-knowledge-graph-schema.md) |
| Assemble | `GraphAssembler` | merged graph + cross-file edges | [ADR-006](adr/ADR-006-knowledge-graph-schema.md) |
| Write | `GraphWriter` | `graph.json` (canonical) + `GraphArtefact` (path, schema_version, sha256) | [ADR-006](adr/ADR-006-knowledge-graph-schema.md), [ADR-007](adr/ADR-007-golden-graph-pattern.md), [ADR-025](adr/ADR-025-manifest-schema-flat-layout.md) |

### The Java parser (sidecar JAR)

`codeograph/parser/java/` is a Maven module that builds `parser.jar` — a JavaParser-based AST extractor invoked as a subprocess per `.java` file. Components:

- `JavaParserRunner` — CLI entry point; reads source file path, writes one JSON envelope to stdout
- `ParsedFileAssembler` — walks the AST and builds the envelope
- `ComplexityCalculator` — cyclomatic complexity, cognitive complexity, CBO (per [ADR-004](adr/ADR-004-complexity-model.md))
- `Lcom4Calculator` — LCOM4 via adjacency list + union-by-size connected components
- `LombokSynthesizer` — synthesises Lombok-generated methods into the AST before extraction (`@Getter`, `@Setter`, `@Data`, `@Value`, `@Builder`, constructors)
- `ParserConstants` — Spring stereotypes, autowire annotations, CBO-excluded types

Regex fallback (`codeograph/parser/regex_fallback.py`) handles malformed sources the AST parser rejects. The dispatcher tags each `ParsedFile` with `extraction_mode: "ast" | "regex"` so consumers can distinguish.

### Output contract

`graph.json` is byte-stable across runs given the same input:

- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` + trailing LF
- Nodes sorted by `id`; edges sorted by `(kind, source, target)`
- Unordered list properties (`modifiers`, `annotations`, `implements`, etc.) sorted within each node
- No timestamps, no run IDs, no absolute paths

`manifest.json` records the SHA-256 of `graph.json` plus schema versions. Tested against checked-in goldens — see [ADR-007](adr/ADR-007-golden-graph-pattern.md) and `tests/test_golden.py`.

### Reproducibility envelope

CI pins `TZ=UTC`, `LC_ALL=C.UTF-8`, `PYTHONHASHSEED=0` (see `.github/workflows/ci.yml`). The JavaParser version is pinned in `pyproject.toml` `[tool.codeograph.versions]`; bumping it requires a goldens refresh.

### Schema

The manifest JSON Schema lives in `codeograph/_generated/manifest.schema.json` — regenerated from the Pydantic source of truth (`codeograph/manifest/schema.py`) via `python -m codeograph.manifest.schema_cli --generate`. CI freshness gate catches drift. Graph and LLM-annotation schemas live in `codeograph/schema/`.

## DC2 — LLM enrichment pipeline

Two passes turn the deterministic graph into `llm-annotations.json`. The whole layer is skipped under `--ast-only` (the manifest records `llm_skipped: true`). Orchestrated by `LlmCorpusEnricher` (`codeograph/analyzer/llm_corpus_enricher.py`).

```
graph.json  →  PASS 1 (per node)  →  PASS 2 (corpus-level)  →  llm-annotations.json
               NodeAnnotator          CorpusSynthesizer
```

| Concern | Component | ADR |
|---|---|---|
| Pass 1 — per-node semantics | `passes/pass1/node_annotator.py` (`NodeAnnotator`) | [ADR-005](adr/ADR-005-token-utilization.md) |
| Pass 2 — corpus synthesis | `passes/pass2/corpus_synthesizer.py` (`CorpusSynthesizer`) | [ADR-005](adr/ADR-005-token-utilization.md) |
| Provider abstraction | `llm/provider.py` (`LlmProvider` ABC), `llm/resolver.py` (`LlmProviderResolver`), `llm/providers/{anthropic,openrouter,openai_compatible}_provider.py` + `langchain_base.py` | [ADR-013](adr/ADR-013-llm-provider-abstraction.md) |
| Middleware stack (decorators over the base provider) | `llm/middleware/{caching,retrying,telemetry}_llm_provider.py` | [ADR-013](adr/ADR-013-llm-provider-abstraction.md), [ADR-015](adr/ADR-015-telemetry-and-response-cache.md) |
| Prompt versioning | `llm/prompts/{loader,renderer,validation,models}.py`; prompt files in `codeograph/prompts/{annotate_node,synthesize_corpus}/` (Markdown + YAML frontmatter, required `content_hash_pin`) | [ADR-014](adr/ADR-014-prompt-versioning.md) |
| Response cache | `llm/cache/{sqlite_backend,key,cache_entry,cache_stats}.py` — local SQLite `cache.db`, 8-component cache key | [ADR-015](adr/ADR-015-telemetry-and-response-cache.md) |
| Telemetry | `telemetry/{jsonl_emitter,session,session_manager,stats_aggregator,telemetry_record}.py` — one structured JSONL row per LLM call | [ADR-015](adr/ADR-015-telemetry-and-response-cache.md) |

v1 supports `ANTHROPIC`, `OPENROUTER`, and `OPENAI_COMPATIBLE` (any OpenAI-compatible endpoint via a configurable `base_url`), defaulting to a single Anthropic Sonnet model across stages; per-stage model overrides (`llm_model_fast` / `deep` / `render`) are configurable, though no curated differential mapping ships in v1. `OLLAMA` and `BEDROCK` are wired in the resolver but raise `NotImplementedError` (v1.1). Calls are synchronous with prompt caching — no Batch API in v1 (ADR-005).

## DC3 — TypeScript/NestJS renderer

`codeograph render` is decoupled from `run`: it reads a prior run output, selects a representative subset of classes within a budget, groups them into domains, and translates each class into idiomatic TypeScript/NestJS source — full method bodies, not skeletons — via one LLM call. The translated files are emitted together with a deterministic Jinja2 project scaffold (`package.json`, `tsconfig.json`, bootstrap `main.ts`); features that cannot be translated faithfully become reviewable TODO/stub or refuse-to-render entries (never silent drops), configurable per feature. Targets are pluggable through a registry.

```
run output  →  ClassSelector  →  DomainGrouping  →  per-class render prompt (LLM)  →  ScaffoldEmitter  →  TS/NestJS project
               (stratified,       (package-prefix
                budget cap)        or manual map)
```

| Concern | Component | ADR |
|---|---|---|
| Renderer contract | `renderers/base.py` (`Renderer[C]` ABC), `renderers/models.py` (`CompileCheck`) | [ADR-008](adr/ADR-008-pluggable-renderer-interface.md) |
| Target registry | `renderers/renderer_registry.py` (`RendererRegistry`, decorator-based registration) | [ADR-008](adr/ADR-008-pluggable-renderer-interface.md) |
| TypeScript/NestJS renderer | `renderers/typescript_nestjs/typescript_renderer.py` (`TypeScriptRenderer`) | [ADR-010](adr/ADR-010-spring-to-typescript-nestjs-mapping.md) |
| Scaffold + per-file prompt | `typescript_nestjs/scaffold_emitter.py` + `templates/scaffold/` (Jinja2), `prompts/render_file/` | [ADR-010](adr/ADR-010-spring-to-typescript-nestjs-mapping.md) |
| Unsupported-feature policy | `typescript_nestjs/feature_policies.py` (translate / stub+TODO / refuse per Spring feature) | [ADR-010](adr/ADR-010-spring-to-typescript-nestjs-mapping.md) |
| Class selection (budget cap) | `rendering/class_selector.py` (`ClassSelector`, stratified High/Medium/Low sampling) | [ADR-009](adr/ADR-009-rendering-budget-cap.md) |
| Domain grouping | `rendering/base.py` (`DomainGrouping` ABC) + `package_prefix_grouping.py` / `manual_mapping_grouping.py` | [ADR-009](adr/ADR-009-rendering-budget-cap.md) |

Rendering calls the LLM once per selected class; a second run against the same corpus hits the response cache (DC2), so there is no additional API cost.

## DC4 — Evaluation & test framework

Eval runs scorecard checks against a run output and writes JSON sidecars to `<out>/evals/`. Two scorecards (graph + code), plus a cross-corpus report.

| Concern | Component | ADR |
|---|---|---|
| Eval orchestration | `evals/corpus_evaluator.py`, `evals/runner.py` | [ADR-017](adr/ADR-017-evaluation-framework.md) |
| Cross-corpus report (`eval report`) | `evals/report.py` | [ADR-017](adr/ADR-017-evaluation-framework.md) |
| Scorecard schema (committed, CI-gated) | `evals/scorecard.schema.json`, `evals/models.py` | [ADR-017](adr/ADR-017-evaluation-framework.md) |
| Graph checks | `evals/checks/graph/` — `structural_completeness`, `internal_consistency`, `relationship_correctness`, `schema_validity`, `reproducibility`, `golden_graph_agreement` (6 deterministic); `semantic_accuracy` reserved (skip → ADR-020, v1.1) | [ADR-017](adr/ADR-017-evaluation-framework.md) |
| Code checks | `evals/checks/code/` — `compile`, `coverage` (feature coverage, not test coverage), `llm_judge` (skip → v1.1) | [ADR-017](adr/ADR-017-evaluation-framework.md) |

Test infrastructure (ADR-018):

| Concern | Where |
|---|---|
| Two layers, mirror layout | `tests/unit/` + `tests/integration/` mirror the `codeograph/` tree |
| Markers | `slow`, `external`, `eval` (declared in `pyproject.toml`; default run deselects all three) |
| Tiered fixtures + goldens | `tests/fixtures/` + `tests/golden/` (byte-equal regression corpus) |
| Test-only LLM | `MockLlmProvider` + `MockLlmProviderBuilder` (`tests/conftest.py`, `tests/fixtures/llm/mock_provider.py`) — no live API calls in v1 |
| Coverage gate | `pytest-cov` line coverage on `codeograph/`, `--cov-fail-under=80` in `pyproject.toml` addopts |

See [ADR-018](adr/ADR-018-test-strategy-with-pytest.md) for the full test strategy.

## DC5 — Run manifest, structured logging, secret scanning

| Component | Location | ADR |
|---|---|---|
| Manifest schema v2.0.0 (flat layout) | `codeograph/manifest/schema.py` | [ADR-025](adr/ADR-025-manifest-schema-flat-layout.md) |
| Manifest IO (strict-on-write / lenient-on-read) | `codeograph/manifest/io.py` | [ADR-025](adr/ADR-025-manifest-schema-flat-layout.md) |
| Run-id generator (`YYYY-MM-DDTHH-MM-SSZ-<6hex>`) | `codeograph/manifest/run_id.py` | [ADR-022](adr/ADR-022-run-manifest-and-structured-logging.md) Fork 3 |
| JSON Schema artefact (committed, CI-gated) | `codeograph/_generated/manifest.schema.json` | [ADR-022](adr/ADR-022-run-manifest-and-structured-logging.md) Fork 7 |
| Dual-emission logging (JSONL file + plaintext stderr) | `codeograph/logging_config.py`, `logging_formatters.py`, `logging_filters.py` | [ADR-022](adr/ADR-022-run-manifest-and-structured-logging.md) Fork 4 |
| Gitleaks secret scanning (pre-commit + CI + nightly) | `.pre-commit-config.yaml`, `.github/workflows/` | [ADR-023](adr/ADR-023-secret-scanning-with-gitleaks.md) |

**Manifest write protocol (ADR-025 amendment):** the manifest is assembled in memory and written **once**, at a terminal checkpoint — after Pass 0 for `--ast-only`, after Pass 1+2 for a full run. A manifest present on disk always satisfies the schema invariants. `eval` and `render` add only top-level optional pointers (`scorecards`, `compile_checks`) to an already-terminal manifest.

## What's next (v1.1)

Go renderer (ADR-011 — learner's design work), error-handling translation (ADR-012), cost-control CLI (ADR-016), snapshot + negative tests (ADR-019), LLM-judge calibration (ADR-020). See the ADR index for the full deferred list.
