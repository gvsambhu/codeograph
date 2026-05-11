# Architecture — current snapshot (DC1)

This page describes what is implemented **today**. It is updated as each delivery chunk (DC) lands. The decision flow that led here lives in [`docs/adr/`](adr/); this page is the snapshot.

## What DC1 delivers

A deterministic pipeline that reads a Java/Spring Boot corpus and emits a canonical knowledge graph (`graph.json`) plus a run manifest (`manifest.json`). AST-only; no LLM enrichment in DC1.

## Pipeline

```
INPUT  →  ACQUIRE  →  DISCOVER  →  PARSE  →  BUILD  →  ASSEMBLE  →  WRITE  →  OUTPUT
 path/         CorpusSpec      ParsedFile     fragment       merged graph     graph.json
 git url/                                     per file                        manifest.json
 zip
```

Each box is a focused class. CLI wires them together (`codeograph/cli/main.py`).

| Stage | Component | Output | ADR |
|---|---|---|---|
| Acquire | `InputAcquirer` + `acquirers/{local,git,zip}` | `CorpusSpec` on local FS | [ADR-002](adr/ADR-002-input-agnostic-design.md) |
| Discover | `SourceDiscoverer` | `ModuleSpec[]` with `java_files[]` | [ADR-002](adr/ADR-002-input-agnostic-design.md) |
| Parse | `FileParserDispatcher` → `JavaFileParser` (JAR subprocess) → `RegexFallback` | `ParsedFile` envelope (TypedDict) | [ADR-003](adr/ADR-003-parsing-strategy.md) |
| Build | `GraphBuilder` | per-file graph fragment | [ADR-006](adr/ADR-006-knowledge-graph-schema.md) |
| Assemble | `GraphAssembler` | merged graph + cross-file edges | [ADR-006](adr/ADR-006-knowledge-graph-schema.md) |
| Write | `GraphWriter` | `graph.json` (canonical) + `manifest.json` (SHA-256) | [ADR-006](adr/ADR-006-knowledge-graph-schema.md), [ADR-007](adr/ADR-007-golden-graph-pattern.md) |

## The Java parser (sidecar JAR)

`codeograph/parser/java/` is a Maven module that builds `parser.jar` — a JavaParser-based AST extractor invoked as a subprocess per `.java` file. Components:

- `JavaParserRunner` — CLI entry point; reads source file path, writes one JSON envelope to stdout
- `ParsedFileAssembler` — walks the AST and builds the envelope
- `ComplexityCalculator` — cyclomatic complexity, cognitive complexity, CBO (per [ADR-004](adr/ADR-004-complexity-model.md))
- `Lcom4Calculator` — LCOM4 via adjacency list + union-by-size connected components
- `LombokSynthesizer` — synthesises Lombok-generated methods into the AST before extraction (`@Getter`, `@Setter`, `@Data`, `@Value`, `@Builder`, constructors)
- `ParserConstants` — Spring stereotypes, autowire annotations, CBO-excluded types

Regex fallback (`codeograph/parser/regex_fallback.py`) handles malformed sources the AST parser rejects. The dispatcher tags each `ParsedFile` with `extraction_mode: "ast" | "regex"` so consumers can distinguish.

## Output contract

`graph.json` is byte-stable across runs given the same input:

- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` + trailing LF
- Nodes sorted by `id`; edges sorted by `(kind, source, target)`
- Unordered list properties (`modifiers`, `annotations`, `implements`, etc.) sorted within each node
- No timestamps, no run IDs, no absolute paths

`manifest.json` records the SHA-256 of `graph.json` plus schema versions. Tested against checked-in goldens — see [ADR-007](adr/ADR-007-golden-graph-pattern.md) and `tests/test_golden.py`.

## Reproducibility envelope

CI pins `TZ=UTC`, `LC_ALL=C.UTF-8`, `PYTHONHASHSEED=0` (see `.github/workflows/ci.yml`). The JavaParser version is pinned in `pyproject.toml` `[tool.codeograph.versions]`; bumping it requires a goldens refresh.

## Schema

JSON Schema files live in `codeograph/schema/`. Pydantic v2 models are code-generated into `codeograph/graph/models/` via `make schema-models`. Both checked in; CI fails if regeneration would change them.

## What's next (not in DC1)

DC2 wires LLM enrichment passes (semantic annotations, domain decomposition) into the same graph. Renderers (TypeScript/NestJS, Go) come later. See the ADR index for committed decisions and the project roadmap for sequence.
