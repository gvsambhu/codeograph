# Codeograph

Reads a Java/Spring Boot codebase and emits a deterministic knowledge graph — nodes, edges, complexity metrics, Spring-aware annotations — reproducible byte-for-byte across runs.

**Status:** v1 complete (DC1–DC5) — deterministic graph, LLM enrichment, eval framework, TypeScript/NestJS renderer, run manifest + structured logging. See [`docs/architecture.md`](docs/architecture.md) for the full pipeline.

## Requirements

- Python ≥ 3.12
- Java 17+ (for the bundled AST parser; regex fallback runs without it)
- Maven 3.9+ (only when rebuilding the parser JAR)

## Quick start

```bash
pip install -e ".[dev]"
codeograph run /path/to/java/project --out ./out
```

Output (three files — always start from `manifest.json`):

| File | Description |
|---|---|
| `out/manifest.json` | Entry point: run identity, `schema_version: "2.0.0"`, SHA-256 of every artefact, `llm_skipped` flag |
| `out/graph.json` | Deterministic AST graph — nodes, edges, complexity metrics |
| `out/llm-annotations.json` | LLM semantic enrichment (full run only; absent on `--ast-only`, indicated by `llm_skipped: true`) |

Input can be a local directory path, a git URL, or a `.zip` archive.

## Running tests

```bash
make test                     # Python unit tests
make lint                     # ruff
make typecheck                # mypy
make golden-update            # refresh Tier 1 / Tier 2 golden graphs

cd codeograph/parser/java
mvn test                      # Java parser tests (JavaParser-based)
```

## Project layout

```
codeograph/                    Python package
  analyzer/                    CorpusAnalyzer — pipeline orchestrator
  cli/                         CLI entry point (run, eval, render, cache)
  config/                      pydantic-settings + YAML config source
  evals/                       eval framework — scorecards, checks, runner, report
  graph/                       GraphBuilder, GraphAssembler, GraphWriter + models
  input/                       corpus acquisition + source discovery
  llm/                         LLM provider, prompts, cache, middleware
  manifest/                    Manifest schema (2.0.0), IO, run_id, schema_cli
  parser/                      FileParserDispatcher, RegexFallback
    java/                      Maven module — builds parser.jar (JavaParser AST)
  passes/                      Pass 1 (annotator), Pass 2 (synthesizer)
  prompts/                     versioned prompt files (annotate_node, synthesize_corpus)
  renderers/                   pluggable renderer registry; typescript_nestjs/
  rendering/                   class selection + domain grouping (ADR-009)
  scripts/                     verify_gitleaks_pin + operational scripts
  telemetry/                   JSONL LLM telemetry emitter + aggregation
_generated/
  manifest.schema.json         committed JSON Schema (regenerated from Pydantic)
docs/
  architecture.md              current architecture snapshot
  adr/                         architecture decision records (ADR-001..026)
tests/
  fixtures/codeograph-corpus/  Tier 1 surgical fixture
  goldens/tier1/               stored golden graphs (byte-equal regression)
  ...                          unit tests mirror codeograph/ layout
```

## LLM Features (DC2)

Codeograph includes an LLM enrichment pipeline (Passes 1 and 2) that adds semantic understanding to the deterministic AST graph:

- **Annotated Graph Output:** Detailed per-node semantics (Pass 1) and corpus-level synthesis (Pass 2) stored in `llm-annotations.json`.
- **Response Cache:** A local SQLite cache (`cache.db`) stores responses. You can manage the cache using the `codeograph cache` CLI (e.g., `codeograph cache stats` or `codeograph cache purge`).
- **Telemetry:** Every LLM call is recorded as a structured JSONL row in the `telemetry/` output folder, carrying token usage, latency, and cache-hit details.

The graph tells Codeograph what is there — nodes, edges, framework semantics, and metrics from precise, reproducible deterministic analysis; LLM Pass 1 explains what it means at the per-node level. The LLM passes matter because they add the layer deterministic analysis cannot supply — per-node explanation, onboarding summaries, and role inference grounded in that verified structure, making the graph easier to read and more useful without changing what the system treats as truth. LLM Pass 2 reaches into riskier corpus-level synthesis, but all LLM output stays advisory in separate artefacts and is contained so the deterministic graph stays authoritative.

## Rendering (DC3)

`codeograph render` converts an existing run output into a TypeScript/NestJS project: each selected class is translated into **full idiomatic NestJS source — method bodies included, not skeletons** — via one LLM call, emitted alongside a deterministic Jinja2 project scaffold (`package.json`, `tsconfig.json`, bootstrap `main.ts`). Features v1 cannot translate faithfully surface as reviewable **TODO/stub** placeholders or explicit **refuse-to-render** entries — never silent drops — under a configurable per-feature policy. Rendering is decoupled from LLM execution so you can tune rendering parameters (ORM mode, class budget, domain grouping) without re-running the expensive annotation passes.

```bash
codeograph render --from ./out --out ./ts-out --target typescript
```

Key flags:

| Flag | Default | Description |
|---|---|---|
| `--from DIR` | required | Output directory from a prior `codeograph run` |
| `--out DIR` | required | Destination for the rendered TypeScript project |
| `--target` | `typescript` | Renderer target (`--list-targets` prints registered targets) |
| `--db-layer` | config default | Override ORM mode: `typeorm`, `typeorm_raw_sql`, or `hybrid` |
| `--render-budget N` | config default | Per-domain class cap (stratified sampling, ADR-009) |
| `--no-scaffold` | off | Skip NestJS scaffold files (package.json, tsconfig, etc.) |
| `--force` | off | Overwrite `--out` if non-empty |

Rendering calls the LLM once per selected class. The second run against the same corpus hits the response cache — no additional API cost.

## Evaluation (DC4)

`codeograph eval` runs scorecard checks against an existing run output. Scorecards are JSON sidecar files written to `<out>/evals/`.

```bash
# Single-corpus scorecard
codeograph eval run ./out

# Cross-corpus comparison across multiple runs
codeograph eval report ./run1 ./run2 ./run3
```

`eval run` options:

| Flag | Description |
|---|---|
| `--scorecard graph\|ts` | Restrict to specific scorecards (default: all) |
| `--check <id>` | Run only the named check IDs |
| `--skip-check <id>` | Skip named check IDs |

The graph scorecard runs 6 deterministic checks (node count, edge count, schema version, sha256 integrity, complexity metrics present, golden-graph agreement). The code-quality scorecard runs 3 checks (compilation, feature coverage, llm_judge — the latter two are `skip` in v1 pending ADR-020 calibration).

You can also run eval automatically as part of `codeograph run` using `--eval`:

```bash
codeograph run /path/to/project --out ./out --eval
```

## Logging (DC5)

Codeograph emits logs via two channels simultaneously:

- **Console (stderr):** Human-readable plaintext, default level `INFO`. Format: `[area] message`.
- **File (`<out>/logs.jsonl`):** Structured JSONL at `DEBUG` level, always written during a `run`. Fields: `run_id`, `logger`, `context`, `level`, `ts`, `msg`.

Log level is controlled via global flags (before the subcommand):

```bash
codeograph -v run ...        # DEBUG console output
codeograph -q run ...        # WARNING only
codeograph -qq run ...       # ERROR only
codeograph --log-level DEBUG run ...   # explicit level (wins over -v/-q)
```

The run manifest (`manifest.json`) is written once at the terminal checkpoint, after all passes complete. It records the `run_id`, artefact SHA-256s, schema version (`2.0.0`), and optional pointers to scorecards and compile-checks. The committed JSON Schema at `codeograph/_generated/manifest.schema.json` is the external validator contract; a CI gate keeps it in sync with the Pydantic source.

## Limitations (v1)

- **Maven-only classpath resolution.** Gradle projects are detected and source files are parsed, but classpath resolution falls back to source-only mode. Method-call resolution is lower fidelity for Gradle inputs until v1.1.
- **TypeScript/NestJS renderer only.** The Go renderer (ADR-011) is planned for v1.1.
- **Anthropic (Claude) only — single model.** All v1 LLM calls use one Sonnet model. Ollama and Bedrock providers are wired but raise `NotImplementedError`; per-stage model selection (separate models for Pass 1 / Pass 2 / hazards) is v1.1.
- **Sync LLM calls; no Batch API.** All LLM calls are synchronous with prompt caching. The Anthropic Batch API (50% discount) is v1.1.
- **CI runs on Linux only.** Local tests pass on Windows/macOS; the automated CI infrastructure runs on `ubuntu-latest`. Multi-OS CI is a v1.1 extension wired by contributor demand.
- **No live-LLM tests.** The test suite uses a deterministic `MockLlmProvider`. No tests make live API calls in v1; the 80% line coverage gate applies to `codeograph/`.
- **Eval covers two committed corpora.** `spring-rest-sample` and `spring-blog-api` are the baseline corpora; `codeograph eval report` provides cross-corpus comparison. Additional corpora can be added to `examples/` per `CONTRIBUTING.md`.
- **`semantic_accuracy` and `llm_judge` checks are skipped in v1.** The graph scorecard reserves these slots; calibration data and the LLM-judge harness land in v1.1 (ADR-020).
- **Coverage check means feature coverage, not test coverage.** The code-quality scorecard `coverage` check measures which Spring annotation categories from the ADR-010 audit were translated into TypeScript — not pytest line coverage.
- **Per-run output is `<out>` itself.** There is no `--runs-dir` flag. Each `codeograph run` invocation owns its `--out` directory. To keep multiple run histories, use distinct `--out` paths (e.g. `--out ./runs/$(date -u +%Y-%m-%dT%H-%M-%SZ)/`).
- **Manifest schema is strict-additive within `2.x`.** Field removal, rename, type-change, or required/optional flips require a `3.0.0` major bump and a superseding ADR. New fields land as minor bumps. External consumers can pin a `2.x` validator and rely on forward compatibility.
- **No log rotation or color output in v1.** `logs.jsonl` grows unboundedly per run; no log-level env-var override. These are v1.1 items.
- **Gitleaks secret scanning is enforced in CI; merges are blocked on detection; no admin bypass.** The `pre-commit` hook is opt-in (`pre-commit install` after setup); CI is the mandatory gate. The gitleaks version is exact-pinned in both `secrets-scan.yml` and `.pre-commit-config.yaml` with a CI parity check, and a scheduled full-history scan runs nightly (non-blocking). See `CONTRIBUTING.md` for the finding-response runbook.
- **Output stability tracks `schema_version`, not the application version.** The app version (`codeograph --version`, currently `0.5.0`) and the artefact `schema_version` are independent version lines. Consumers scripting against `graph.json` / `manifest.json` should pin or check `schema_version`; the app version is not a format-stability guarantee. v1 ships in `0.x` — `1.0.0` is published only at the stability gate (ADR-026).

## Documentation

- [Architecture snapshot](docs/architecture.md) — what's wired today
- [ADRs](docs/adr/) — design decisions and their rationale
- [Contributing](CONTRIBUTING.md) — commit conventions, branching, CI
