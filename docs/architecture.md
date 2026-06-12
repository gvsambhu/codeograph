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
