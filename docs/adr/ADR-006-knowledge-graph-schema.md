---
status: proposed
date: 2026-04-30
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-006 — Knowledge Graph Schema

## Context and Problem Statement

Codeograph's pipeline produces a knowledge graph as its central artifact: AST-derived structural facts (classes, methods, calls, complexity) from ADR-003, plus LLM-derived semantic annotations (domain labels, NL summaries, migration hazards) from ADR-005. Stage 4 of the pipeline materialises this graph on disk so that:

* the v1 TypeScript/NestJS renderer (ADR-010) and v1.1 Go renderer (ADR-011) can consume it,
* the golden-graph regression suite (ADR-007) can deep-equal across runs,
* the run manifest (ADR-022) can fingerprint and reproduce outputs,
* a portfolio reviewer or future contributor can read the artifact and understand the system.

Multiple representation choices are open and they interact: how the schema is authored (Pydantic-first vs JSON-Schema-first), how the graph is laid out on disk (nested document vs flat node/edge vs streaming), how nodes are identified, how edges are modelled, how LLM outputs sit alongside deterministic AST data, how versions are tracked, and what extension points are reserved for v1.1 additions.

The constraints are concrete:

* Realistic Codeograph inputs span ~10² classes (single Spring Boot service) to ~10⁴ classes (large modular monolith) per ADR-005's revised N analysis. The schema must work at both ends.
* Multi-language consumers are a v1 commitment (TS) and a v1.1 commitment (Go); the schema must be language-neutral.
* AST-derived facts are deterministic; LLM-derived facts are not. ADR-021 (v1.1) will formalise the determinism contract — ADR-006 must draw the boundary cleanly so ADR-021 has something to point at.
* ADR-003 produces a `ClassFacts` intermediate dataclass; the on-disk schema is downstream of this.
* ADR-022 (run manifest) is in scope as part of the same artefact set; versioning policy can leverage it.

This ADR pins seven decisions: schema authoring tool, graph format, node identity, edge model, LLM-output placement, versioning policy, and v1.1 extension points.

## Decision Drivers

* **Multi-language consumability** — TS today, Go in v1.1. The contract should be language-neutral.
* **Determinism boundary clarity** — deterministic AST output and probabilistic LLM output must be distinguishable, ideally at the file level.
* **Renderer ergonomics** — per-class iteration is the dominant access pattern; "give me class X with its inheritance and methods" should be one or two lookups.
* **Golden-graph testability (ADR-007)** — deep-equal must be tractable; LLM noise must not corrupt it.
* **Future Neo4j compatibility** — speculative but on the table; the graph shape should not actively block it.
* **Schema discipline** — every change should pass through a deliberate review, not slip in via an open-extensions slot.
* **Portfolio signal** — the schema is a visible artifact; design choices read as architectural maturity (or lack of it).
* **YAGNI** — v1 schema should serve v1 needs, not pre-declare v1.1 features.

## Considered Options

Each fork below was evaluated against the drivers. Options that were considered and rejected appear in the Pros and Cons section at the end.

### Fork 1 — Schema authoring tool

* (a) Pydantic models canonical, JSON Schema generated on demand.
* (b) JSON Schema canonical, Python validates via `jsonschema` library, no Pydantic models for graph payloads.
* (c) Both hand-written, kept in sync manually.
* **(d) JSON Schema canonical, Pydantic models generated via `datamodel-code-generator`, CI-enforced freshness check.** ✅

### Fork 2 — Graph format

* (a) Single nested JSON document (`modules → classes → methods`).
* **(b) Flat node/edge lists (property-graph style: `nodes[]` + `edges[]`).** ✅
* (c) JSONL stream (one record per line) — deferred to v1.1.

### Fork 3 — Node identity

* **(a) FQCN-based string IDs.** ✅
* (b) Hash-based opaque IDs (e.g. `c_8f3a9b2e`).
* (c) Integer auto-increment.

### Fork 4 — Edge model

* (a) Maximalist edges — every relationship including `extends` is an edge record.
* (b) Minimalist edges — most structural relationships as node properties; only cross-cutting as edges.
* **(c) Hybrid — inheritance/modifiers/stereotype as node properties; containment/calls/depends_on/autowires as edges.** ✅

### Fork 5 — LLM-output placement

* (a) Inline on each class node.
* (b) Sidecar `llm_annotations` block in the same file.
* **(c) Separate file (`out/graph.json` + `out/llm-annotations.json`).** ✅

### Fork 6 — Versioning

* (a) `schema_version` field at the root of each file.
* (b) Version embedded in filename.
* (c) Both field and filename.
* **(d) Manifest (`out/manifest.json`) as the single source of truth.** ✅

### Fork 7 — v1.1 extension points

* (a) `extensions` open object on every node.
* (b) Reserved top-level keys (null-valued in v1).
* **(c) Pure semver — no reserved slots; v1.1 additions trigger schema bumps tracked in the manifest.** ✅
* (d) Hybrid — per-node additions in `extensions`, structural additions force a bump.

## Decision Outcome

### Fork 1 — Schema authoring tool: (d) JSON Schema canonical, Pydantic generated

JSON Schema files under `codeograph/schema/` are the language-neutral source of truth. Pydantic v2 models are generated into `codeograph/graph/_generated_models.py` via `datamodel-code-generator`. A `make schema-models` target regenerates them; CI fails if the generated file would change (i.e., if the developer forgot to regenerate after a schema edit).

```bash
datamodel-codegen \
  --input codeograph/schema/ \
  --output codeograph/graph/_generated_models.py \
  --output-model-type pydantic_v2.BaseModel
```

Python writers and readers use the generated Pydantic models for type-checked access. External consumers (TS renderer in v1, Go renderer in v1.1) consume the `.schema.json` files directly via `quicktype`, `json-schema-to-typescript`, or `go-jsonschema`.

### Fork 2 — Graph format: (b) Flat property-graph

`graph.json` carries two top-level arrays:

```json
{
  "nodes": [
    {"id": "...", "type": "...", "...": "..."}
  ],
  "edges": [
    {"type": "...", "from": "...", "to": "...", "...": "..."}
  ]
}
```

Node `type` discriminates between `module`, `class`, `method`, `field`, etc. Edge `type` discriminates between `contains`, `calls`, `depends_on`, `autowires`, etc. This is the property-graph standard used by Neo4j, JanusGraph, GraphSON, and Memgraph imports.

JSONL streaming is explicitly deferred. When v1.1 needs it (large monoliths, partial output, append-only crash recovery), a `--format=jsonl` flag emits the same node/edge shapes one-per-line. The data shapes do not change — only the envelope.

### Fork 3 — Node identity: (a) FQCN-based strings

Identity conventions:

| Node kind | ID format | Example |
|---|---|---|
| Module | `mod:<module-name>` | `mod:order-service` |
| Class | `<fqcn>` (with `$` for inner classes) | `com.acme.order.OrderService` |
| Method | `<class-fqcn>#<method-name>(<param-types>)` | `com.acme.order.OrderService#placeOrder(java.lang.String,int)` |
| Field | `<class-fqcn>.<field-name>` | `com.acme.order.OrderService.transactionTemplate` |

Param types use Java fully-qualified names to disambiguate overloads. The `$` separator for inner classes follows JVM bytecode convention (`Outer$Inner`).

For Neo4j use, the FQCN goes into a property called `id` on a generically-labelled node (`:Class`, `:Method`); special characters (`#`, `(`, `,`, `<>`, `$`) are safe inside string property values and string literals in Cypher queries. Backtick-quoting is not needed because FQCNs do not appear as labels or relationship types.

### Fork 4 — Edge model: (c) Hybrid

The rule: **node properties describe what something is; edges describe how it relates.**

| Concept | Storage | Rationale |
|---|---|---|
| `kind` (class/interface/enum/record) | property | attribute of the class itself |
| `modifiers` (public, abstract, …) | property | attribute |
| `extends` (single supertype) | property (string FQCN) | attribute; cardinality 1; mirrors ClassFacts |
| `implements` (interfaces) | property (array of FQCNs) | attribute; mirrors ClassFacts |
| `stereotype` (Service / Controller / …) | property | attribute |
| `complexity` (CC, cognitive, WMC, …) | property | attribute (raw integers per ADR-004 TP-d) |
| `contains` (module → class, class → method) | edge | graph spine; bidirectionally traversed |
| `calls` (method → method) | edge | core graph relationship |
| `depends_on` (class → class) | edge | core graph relationship |
| `autowires` (Spring DI) | edge | first-class Spring relationship |
| `annotated_with` | edge | many-to-many traversable |

For Neo4j import, a small materialisation step can convert `extends`/`implements` properties into `:EXTENDS` / `:IMPLEMENTS` relationships if the user wants symmetric Cypher traversal. This is a 5-line `UNWIND` query, not a schema burden on v1.

### Fork 5 — LLM-output placement: (c) Separate file

```
out/
├── manifest.json
├── graph.json              ← deterministic AST + complexity + edges (Fork 4)
└── llm-annotations.json    ← non-deterministic LLM output, keyed by node id
```

`graph.json` carries no LLM-derived fields. `llm-annotations.json` is keyed by class-level node id and contains domain label, NL summary, migration hazards, plus the `extraction_mode` tag from ADR-005 (`whole_class` / `signatures_only` / `llm_failed`) and prompt-version metadata from ADR-014.

```json
// llm-annotations.json
{
  "graph_ref": "graph.json",
  "annotations": {
    "com.acme.order.OrderService": {
      "domain_label": "checkout",
      "nl_summary": "Coordinates order placement and payment.",
      "migration_hazards": [...],
      "extraction_mode": "whole_class",
      "model": "claude-sonnet-4-6",
      "prompt_version": "p1.v3"
    }
  }
}
```

The renderer loads both files via the manifest and joins by id at consumption time.

### Fork 6 — Versioning: (d) Manifest-only

`manifest.json` is the canonical entry point. It declares the version of every artefact, plus a SHA-256 of each file for integrity:

```json
{
  "manifest_version": "1.0.0",
  "codeograph_version": "0.3.0",
  "generated_at": "2026-04-30T08:15:00Z",
  "run_id": "run_2026-04-30T08-15-00Z_a4b8",
  "artifacts": {
    "graph": {
      "path": "graph.json",
      "schema_version": "1.0.0",
      "sha256": "..."
    },
    "llm_annotations": {
      "path": "llm-annotations.json",
      "schema_version": "1.0.0",
      "sha256": "..."
    }
  }
}
```

Files (`graph.json`, `llm-annotations.json`) carry no `schema_version` field of their own. The contract is "read manifest first, then dispatch on declared schema versions." This eliminates the liar risk of duplicated version metadata and aligns with how Docker images, npm lockfiles, OCI artefacts, and BIDS scientific datasets work.

**Canonical-form requirement.** The `sha256` hashes are computed over the *canonical-form* serialization of each artefact, not arbitrary bytes. Canonical form is defined by `codeograph/graph/writer.py::canonical_serialize`:

* `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
* trailing newline (`\n`) at end of file
* LF line endings (enforced by `.gitattributes` rule `*.json text eol=lf`)
* nodes sorted by `id`; edges sorted by `(type, from, to)`
* node-property arrays (`implements`, `modifiers`, etc.) sorted before emission
* no wall-clock timestamps, run ids, or absolute filesystem paths anywhere in `graph.json` (those live in the manifest)
* JavaParser version pinned in `pyproject.toml`; upgrades are explicit goldens-refresh events, not silent drift

The contract is testable: a CI check runs the writer twice on the same input and asserts byte-identical output. The same canonical-form bytes power both the manifest `sha256` integrity hash and the byte-equal comparison used by golden-graph testing in ADR-007.

ADR-022 will own the manifest's other responsibilities (run-level structured logging, reproducibility); this ADR pins only the version-tracking contract.

### Fork 7 — v1.1 extension points: (c) Pure semver

The v1 schema reserves no slots for v1.1 additions — no `extensions` open object, no null-valued reserved keys, no speculative scaffolding. When v1.1 introduces go-idiom hints (ADR-011), exception-flow edges (ADR-012), per-class cost actuals (ADR-016), determinism flags (ADR-021), or safety annotations (ADR-024), each addition triggers a schema version bump tracked in the manifest.

The bump granularity is per-artefact: `graph.json` may bump to 1.1.0 while `llm-annotations.json` stays at 1.0.0, and the manifest records both. ADR-022 readers route per-artefact based on the manifest's declared versions.

This forces every v1.1 schema addition through a deliberate ADR. There is no path by which a field slips in without a design conversation.

### Orchestration constraint flagged for ADR-022

This ADR depends on ADR-022 for manifest semantics: the version-tracking contract assumes `manifest.json` exists and is authoritative. ADR-022 must honour the artefact-listing shape declared here. If ADR-022 chooses a different manifest format, this ADR's Fork 6 decision is re-opened.

## Consequences

**Positive.**

* Language-neutral schema artefacts (`schema/*.json`) — TS and Go renderers consume the same contract Python does.
* Type-checked Python access via generated Pydantic models, with CI freshness check preventing drift.
* Property-graph format aligns Codeograph with mature graph-tool ecosystem; future Neo4j integration is a 5-line import script away.
* Determinism boundary is a file boundary — golden-graph testing (ADR-007) compares `graph.json` only, never has to mask LLM fields.
* Prompt iteration during ADR-014 prompt tuning is fast: re-run only Pass 1, only `llm-annotations.json` changes, `graph.json` stays cached.
* Partial output is coherent — if Pass 1 fails for some classes, `graph.json` is still complete and `llm-annotations.json` documents the gaps via `extraction_mode: llm_failed`.
* Manifest-only versioning eliminates duplicated metadata and provides cryptographic file-pairing integrity via SHA-256.
* Canonical-form serialization is testable in CI (writer runs twice on the same input, output must be byte-identical), giving an automated guard against accidental non-determinism.
* Pure semver discipline means every schema change is a deliberate ADR moment.

**Negative.**

* Two output files instead of one, plus a manifest. Renderer must load three files (manifest → graph + llm-annotations). Mitigated: manifest path is conventional; loader is ~10 lines.
* `graph.json` cannot be read standalone — the manifest is required to know its schema version. For one-off ad-hoc consumption ("just give me the graph"), this is friction. Mitigated: manifest is always co-located.
* Codegen step (`datamodel-code-generator`) adds a build dependency. Mitigated: standard tool, well-supported.
* Pure semver means v1.0 readers cannot open v1.1 files. Mitigated: not a real loss — there is no installed base of v1.0 readers to support.
* FQCN string IDs are larger than hash IDs. At expected scales (300–8K classes), this is manageable; at 10K+ classes the file size cost becomes noticeable but not prohibitive.
* Edge-model hybrid means `extends`/`implements` need a small materialisation step for symmetric Cypher traversal. Documented as the trade-off.
* JavaParser version upgrades produce content drift (line numbers, parameter type strings, generic representations can shift), forcing deliberate goldens refresh on every dep bump. Pinned in `pyproject.toml`; upgrades are explicit, reviewer-visible events.
* Writer-side canonical-form discipline (sorted keys, sorted arrays, no leaked non-determinism) must be maintained for every new field type. CI double-write check enforces it but does not prevent the discipline lapse from happening in the first place.

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. **Schema files in repo** — `codeograph/schema/` contains hand-written JSON Schema for all node and edge types, manifest, and llm-annotations.
2. **Generated models present and fresh** — `codeograph/graph/_generated_models.py` exists; CI runs `datamodel-code-generator` and fails on diff.
3. **Sample run reproduces shape** — running Codeograph against `spring-petclinic` produces `out/manifest.json`, `out/graph.json`, `out/llm-annotations.json` matching the declared schemas.
4. **Golden-graph test (ADR-007) deep-equals `graph.json` only** — no LLM-field masking required.
5. **Renderer (ADR-010) loads via manifest** — TS renderer calls `manifest.json` first, then dispatches per declared schema version.
6. **Schema-version bump test** — a deliberate v1.0 → v1.1 bump simulation confirms manifest-driven dispatch works.

## Pros and Cons of the Considered Options

### Fork 1 — Schema authoring tool

**(a) Pydantic canonical, JSON Schema generated.**
* Good, because single source of truth in Python.
* Good, because runtime validation is native.
* Bad, because the schema artefact is a generated byproduct, not a curated contract — weaker portfolio signal for "designed for multi-language."
* Bad, because Pydantic-to-JSON-Schema export has quirks (discriminated unions, `Literal` handling).

**(b) JSON Schema canonical, validated via `jsonschema`.**
* Good, because schema is the canonical, language-neutral contract.
* Good, because external readers (TS, Go, portfolio reviewer) read a curated file.
* Bad, because Python writers lose type checking — graph nodes become `dict[str, Any]`.
* Bad, because every field access is a runtime dictionary lookup.

**(c) Both hand-written.**
* Good, because each artefact can be curated for its audience.
* Bad, because drift between the two is high-risk and CI equality assertions are fragile.
* Bad, because every change requires updating two files.

**(d) JSON Schema canonical, Pydantic generated. ✅ Chosen.**
* Good, because schema is language-neutral and curated.
* Good, because Python writers get type-checked access via generated models.
* Good, because there is no manual sync — codegen is deterministic.
* Good, because the pattern matches OpenAPI / FastAPI codegen workflows (industry-aligned).
* Bad, because adds a build dependency on `datamodel-code-generator` and a CI freshness check.
* Bad, because generated Python models can be slightly less idiomatic than hand-written ones (fewer custom validators, plain field types).

### Fork 2 — Graph format

**(a) Single nested JSON document.**
* Good, because human-readable diff is excellent — locality of related data.
* Good, because renderer ergonomics are strong (object graph mirrors mental model).
* Bad, because schema complexity is high (modules contain classes contain methods…).
* Bad, because pretends Codeograph is not a graph tool — weak portfolio signal.
* Bad, because Cypher / Neo4j import requires a flatten step.

**(b) Flat node/edge property-graph. ✅ Chosen.**
* Good, because schema is simplest (one node shape, one edge shape).
* Good, because matches property-graph industry standard (Neo4j, JanusGraph, Memgraph).
* Good, because portfolio signal is strongest: "Codeograph is a graph tool that emits graph data."
* Bad, because edges repeat IDs, increasing file size.
* Bad, because human-readable diff is more scattered than nested.

**(c) JSONL stream.**
* Good, because streaming consumption — large monoliths fit in memory.
* Good, because append-only writing supports crash recovery and partial output.
* Bad, because golden-graph testing requires canonicalising line order.
* Bad, because diff readability suffers (one record per line).
* Bad, because v1 does not yet need streaming; deferring to v1.1 is YAGNI-correct.

### Fork 3 — Node identity

**(a) FQCN-based strings. ✅ Chosen.**
* Good, because human-debuggable at every level (logs, diffs, Cypher queries).
* Good, because cross-graph merge is collision-free by JVM uniqueness rules.
* Good, because Cypher queries against FQCN ids are readable.
* Bad, because larger ID size repeated across many edges.
* Bad, because special characters require escaping when used outside string property values.

**(b) Hash-based.**
* Good, because compact and special-char-safe.
* Bad, because not human-debuggable — every debug session needs a lookup table.
* Bad, because requires 8-byte hash for collision-safe scale (10K nodes).

**(c) Integer auto-increment.**
* Good, because shortest IDs.
* Bad, because not stable across runs unless visit order is deterministic.
* Bad, because cross-graph merge requires renumbering — multi-module aggregation (ADR-002) is broken.
* Bad, because not human-debuggable.

### Fork 4 — Edge model

**(a) Maximalist edges.**
* Good, because schema is uniform (one node shape, one edge shape).
* Good, because every relationship is queryable in Neo4j.
* Bad, because flattens semantically distinct concepts (`contains`, `extends`, `calls`) into one shape.
* Bad, because at odds with how Java developers think about inheritance.

**(b) Minimalist edges.**
* Good, because mirrors ClassFacts dataclass shape.
* Good, because renderer "give me class X" is one lookup.
* Bad, because Neo4j queries are asymmetric (`:CALLS` works, `:EXTENDS` does not).
* Bad, because reverse-traversal ("what extends X?") is a full scan.

**(c) Hybrid. ✅ Chosen.**
* Good, because matches how working code-graph tools (jQAssistant, Structure101) model Java.
* Good, because rule is clear and ADR-defensible: "properties describe attributes; edges describe relationships."
* Good, because containment-as-edge is the right call for the graph spine.
* Good, because v1.1 additions (autowires, transactional boundaries, exception flows) land naturally as new edge types.
* Bad, because requires a small materialisation step for symmetric Neo4j inheritance traversal.
* Bad, because schema has two storage rules instead of one.

### Fork 5 — LLM-output placement

**(a) Inline on class node.**
* Good, because renderer "give me class X" is one lookup.
* Good, because schema is simplest — one shape carries everything.
* Bad, because golden-graph testing (ADR-007) must mask LLM fields — fragile.
* Bad, because deterministic and probabilistic data are mixed at the node level.
* Bad, because re-running just LLM passes rewrites the whole graph file.

**(b) Sidecar block, same file.**
* Good, because some separation between deterministic and LLM data.
* Good, because golden-graph testing skips one block instead of fields-per-node.
* Bad, because still couples deterministic and LLM data into one file's lifecycle.
* Bad, because re-running LLM still rewrites the whole file.

**(c) Separate file. ✅ Chosen.**
* Good, because determinism boundary is a file boundary — clearest possible separation.
* Good, because golden-graph testing compares `graph.json` only, no masking required.
* Good, because re-running LLM passes only rewrites `llm-annotations.json` — fast prompt iteration.
* Good, because failure mode is naturally handled (partial outputs are coherent).
* Good, because matches industry pattern (tree-sitter, Babel, ESLint split structure from analysis).
* Bad, because renderer loads two files instead of one.
* Bad, because cross-file id-join is required at consumption time.

### Fork 6 — Versioning

**(a) Field at root.**
* Good, because canonical, JSON-native.
* Good, because survives file rename or move.
* Bad, because not visible without opening the file.
* Bad, because each artefact carries its own version metadata, no integrity check across artefacts.

**(b) Filename only.**
* Good, because visible at a glance.
* Good, because side-by-side coexistence is natural.
* Bad, because lost on rename.
* Bad, because requires path-parsing to dispatch.

**(c) Both.**
* Good, because all of (a) and (b)'s benefits.
* Bad, because liar risk — filename and field can disagree.
* Bad, because duplication.

**(d) Manifest-only. ✅ Chosen.**
* Good, because single source of truth, no duplication.
* Good, because manifest is already required by ADR-022 — piggy-backing version metadata is free.
* Good, because SHA-256 hashes provide cryptographic file-pairing integrity.
* Good, because matches Docker / npm / OCI / BIDS handling.
* Good, because filenames stay clean.
* Good, because the canonical-form bytes that produce the SHA-256 are the same bytes used by ADR-007 byte-equal golden testing — one contract, two uses.
* Bad, because individual files cannot be read standalone — manifest is mandatory.
* Bad, because requires ongoing writer-side canonical-form discipline (sorted keys, sorted arrays, no leaked non-determinism); enforced by CI double-write check but discipline must hold across every new field type.

### Fork 7 — v1.1 extension points

**(a) `extensions` open object.**
* Good, because forwards-compatible — v1 readers ignore unknown extensions.
* Good, because per-node v1.1 additions land trivially.
* Bad, because junk-drawer risk is high — anything can land in `extensions` without an ADR.
* Bad, because clutters every v1 node with `"extensions": {}`.

**(b) Reserved nulls.**
* Good, because pre-declares known v1.1 features clearly.
* Bad, because YAGNI violation — committing to specific futures before designing them.
* Bad, because guesses may be wrong; reserved slots become dead weight.

**(c) Pure semver. ✅ Chosen.**
* Good, because cleanest v1 schema — no speculative scaffolding.
* Good, because forces every v1.1 addition through a deliberate ADR and version bump.
* Good, because matches semver / JSON Schema / GeoJSON / OpenAPI 3.x convention.
* Good, because manifest already supports independent per-artefact versioning (Fork 6 = d).
* Bad, because v1.0 readers cannot open v1.1 files (acceptable — no installed base).
* Bad, because every addition requires migration consideration.

**(d) Hybrid.**
* Good, because per-node additions are cheap; structural additions force ADR.
* Bad, because creates two evolution paths, which is more rules to remember.
* Bad, because per-node additions slip in without an ADR moment, undermining discipline.

## More Information

**Relationships to other ADRs.**

* **ADR-002** (input-agnostic design) supplies the multi-module enumeration that `mod:<module-name>` ids reference, and the module → class containment edge.
* **ADR-003** (parsing strategy) supplies the `ClassFacts` intermediate dataclass; this ADR translates that shape into on-disk node and edge records, including the `extraction_mode` tag (`ast` / `regex_fallback`) carried as a node property.
* **ADR-004** (complexity model) supplies the six raw-integer metrics carried as `complexity` node properties, per the TP-d threshold policy.
* **ADR-005** (token utilization) supplies the LLM-output payload (domain label, NL summary, migration hazards), the second `extraction_mode` tag (`whole_class` / `signatures_only` / `llm_failed`), and the prompt-version reference. These all live in `llm-annotations.json`, not `graph.json`.
* **ADR-007** (golden-graph pattern) is the primary consumer of `graph.json` — deep-equality testing relies on the determinism boundary drawn here.
* **ADR-010** (Spring → TS/NestJS mapping, v1) is a primary downstream consumer; the renderer loads `manifest.json` and dispatches per declared schema version.
* **ADR-011** (Spring → Go mapping, v1.1) is the second multi-language consumer; reads the same `schema/*.json` artefacts via Go codegen.
* **ADR-013** (LLM provider abstraction) — orthogonal, but its prompt outputs land in `llm-annotations.json`.
* **ADR-014** (prompt versioning) supplies the `prompt_version` field carried in `llm-annotations.json` per-class.
* **ADR-021** (determinism contract, v1.1) extends the determinism boundary drawn here with a manifest-level fingerprint.
* **ADR-022** (run manifest + structured logging) owns the broader manifest semantics; this ADR pins the version-tracking subset.

**Deferred items.**

* JSONL streaming output format (Fork 2 v1.1 path) — `--format=jsonl` flag emitting same node/edge shapes one-per-line.
* `extends` / `implements` materialisation as Neo4j relationships — small import-side script when needed.
* Schema migration tooling — when v1 → v1.1 bumps land, a `codeograph migrate` subcommand can transform v1 outputs in place. Not in v1 scope.
* `display_name` field on nodes for human-facing rendering — useful when FQCN ids are too verbose; deferred until renderer (ADR-010) demonstrates the need.

**References.**

* JSON Schema draft 2020-12 — https://json-schema.org/draft/2020-12/schema
* `datamodel-code-generator` — https://github.com/koxudaxi/datamodel-code-generator
* Neo4j property-graph model — https://neo4j.com/docs/cypher-manual/current/introduction/cypher_neo4j/
* Property graph standards (GraphSON, Apache TinkerPop) — https://tinkerpop.apache.org/
* OpenAPI / FastAPI codegen pattern — Pydantic-from-JSON-Schema workflow as used by FastAPI ecosystem.
* OCI image manifest spec — https://github.com/opencontainers/image-spec/blob/main/manifest.md (reference for Fork 6 manifest pattern).
* BIDS scientific data format — https://bids.neuroimaging.io (reference for manifest-driven multi-artefact data formats).
* Tree-sitter / Babel split between AST and analysis passes — reference for Fork 5 separate-file pattern.
* SemVer 2.0.0 — https://semver.org (reference for Fork 7 versioning policy).

## Amendments

**2026-05-02 — Canonical-form clarification.** Fork 6's `sha256` contract clarified to be over canonical-form serialization rather than arbitrary bytes. Writer rules listed in Decision Outcome → Fork 6 (sorted keys, sorted node and edge arrays, LF endings, no leaked non-determinism, JavaParser version pinned). Adds CI double-write check as testable enforcement. Surfaced during ADR-007 golden-test design, where byte-equal goldens and the manifest sha256 contract were identified as the same constraint and benefit from explicit canonical-form rules. No reversal of any prior decision; clarification only.
