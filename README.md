# Codeograph

Reads a Java/Spring Boot codebase and emits a deterministic knowledge graph — nodes, edges, complexity metrics, Spring-aware annotations — reproducible byte-for-byte across runs.

**Status:** DC1 (AST pipeline) — see [`docs/architecture.md`](docs/architecture.md) for what's implemented today. Later deliveries add LLM enrichment, domain decomposition, and target-language renderers.

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
| `out/manifest.json` | Entry point: schema versions + SHA-256 of each artefact |
| `out/graph.json` | Deterministic AST graph — nodes, edges, complexity metrics |
| `out/llm-annotations.json` | LLM semantic enrichment (DC2+; `sha256: null` in DC1 `--ast-only` output) |

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
  cli/                         CLI entry point (codeograph run)
  config/                      pydantic-settings + YAML config source
  graph/                       GraphBuilder, GraphAssembler, GraphWriter + models
  input/                       corpus acquisition + source discovery
  parser/                      FileParserDispatcher, RegexFallback
    java/                      Maven module — builds parser.jar (JavaParser AST)
  schema/                      JSON Schema files (input to Pydantic codegen)
docs/
  architecture.md              current architecture snapshot (DC1)
  adr/                         architecture decision records (ADR-001..)
tests/
  fixtures/codeograph-corpus/  Tier 1 surgical fixture
  goldens/tier1/               stored golden graphs (byte-equal regression)
  ...                          unit tests mirror codeograph/ layout
```

## Limitations (v1)

- **Maven-only classpath resolution.** Gradle projects are detected and source files are parsed, but classpath resolution falls back to source-only mode. Method-call resolution is lower fidelity for Gradle inputs until v1.1.
- **No LLM enrichment.** `--ast-only` is the only supported mode in DC1. Semantic annotations and domain decomposition land in DC2.
- **No rendering.** TypeScript/NestJS and Go renderers are planned for later deliveries.

## Documentation

- [Architecture snapshot](docs/architecture.md) — what's wired today
- [ADRs](docs/adr/) — design decisions and their rationale
- [Contributing](CONTRIBUTING.md) — commit conventions, branching, CI
