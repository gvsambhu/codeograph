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
  renderers/                   pluggable renderer registry; typescript_nestjs/
  scripts/                     verify_gitleaks_pin + operational scripts
_generated/
  manifest.schema.json         committed JSON Schema (regenerated from Pydantic)
docs/
  architecture.md              current architecture snapshot
  adr/                         architecture decision records (ADR-001..025)
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

> **TODO(learner):** Add a paragraph here framing "Why LLM passes matter" using the project voice.

## Limitations (v1)

- **Maven-only classpath resolution.** Gradle projects are detected and source files are parsed, but classpath resolution falls back to source-only mode. Method-call resolution is lower fidelity for Gradle inputs until v1.1.
- **TypeScript/NestJS renderer only.** The Go renderer (ADR-011) is planned for v1.1.

## Documentation

- [Architecture snapshot](docs/architecture.md) — what's wired today
- [ADRs](docs/adr/) — design decisions and their rationale
- [Contributing](CONTRIBUTING.md) — commit conventions, branching, CI
