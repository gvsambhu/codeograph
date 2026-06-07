---
status: accepted
date: 2026-06-07
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-025 — Manifest Schema 2.0.0 (Flat Layout)

## Context and Problem Statement

The run manifest (`<out>/manifest.json`) is the canonical entry point for every run: it carries
provenance (tool + corpus + run identity), an index of the artefacts produced, per-artefact integrity
hashes, and small per-run aggregates. Consumers read it first and dispatch on its declared versions.

The manifest schema evolved additively across six `1.x` bumps (`1.0` → `1.7`), accreting `cache_stats`,
`scorecards`, `compile_checks`, `source_path`, `corpus_id`, and `run_id` onto an initial **nested**
shape. That accretion left two structural problems the `1.x` line cannot fix additively:

1. **Mis-categorised payloads.** `scorecards` and `compile_checks` are *evaluation outputs*, produced
   by a separate stage from the deterministic + LLM *artefacts* — yet they sit nested *under*
   `artefacts`, conflating two distinct kinds of output.
2. **A weak integrity contract.** `sha256` is nullable on every pointer (to accommodate the
   `--ast-only` run, where no LLM-annotation file is produced), so "no hash" is overloaded to mean both
   "this run skipped LLM passes" and, accidentally, "this artefact has no integrity guarantee."

ADR-022 attempted to lock the manifest's evolution rule (strict-additive within `1.x.x`) **and** a
canonical layout in the same round, but the two are mutually inconsistent: the canonical layout
restructures the shipped `1.7.0` shape, and a restructure is by definition not additive. A restructure
cannot live inside `1.x`.

This ADR resolves the inconsistency by treating the restructure as what it is — a **major version
change** — and locking a clean `2.0.0` manifest schema. It supersedes the manifest decisions of ADR-022
(see Relationships); ADR-022's structured-logging decisions are unaffected.

There is no installed base of external manifest consumers, so the `1.x` → `2.0.0` break carries no
migration burden beyond refreshing the committed example outputs.

## Decision Drivers

* **Readability as a curated artefact** — the manifest is the first thing a reader inspects; its
  top-level shape should reflect the real categories of output (artefacts vs evaluations).
* **No silent failures** — integrity must be a hard guarantee; the "LLM passes were skipped" state must
  be explicit, not inferred from a missing hash.
* **Schema discipline** — a breaking restructure goes through a deliberate major-version bump, after
  which strict-additive evolution resumes.
* **Forward compatibility within v1** — within `2.x.x`, evolution is additive again; old readers keep
  working across minor bumps.
* **Multi-language consumability** — external tooling validates a manifest against a committed JSON
  Schema without importing the producing package.
* **YAGNI** — fields with no v1 capability behind them (cost estimates without a cost model) are not
  shipped; they are added when the capability exists.

## Considered Options

### Fork 1 — Evolution path given the shipped `1.7.0` nested manifest

* (a) Continue strict-additive within `1.x`; keep the nested shape; never restructure in v1.
* (b) Additive migration within `1.x` via a deprecation cycle (old + new fields coexist, old removed later).
* **(c) Restructure into a clean layout as a `2.0.0` major bump; strict-additive resumes within `2.x`. ✅**

### Fork 2 — Placement of evaluation outputs (`scorecards`, `compile_checks`)

* (a) Nested under `artefacts` (the shipped shape).
* **(b) Top-level keys, peers of `artefacts`. ✅**

### Fork 3 — Integrity contract and the `--ast-only` representation

* (a) `sha256` nullable on every pointer; a skipped LLM run leaves a pointer with `sha256: null`.
* (b) `sha256` required; on `--ast-only`, omit the `llm_annotations` pointer entirely (absence = not produced).
* **(c) `sha256` required AND a top-level `llm_skipped` boolean AND omit the `llm_annotations` pointer
  on `--ast-only`. ✅**

### Fork 4 — Per-artefact `schema_version`

* **(a) Retain per-artefact `schema_version` on each artefact pointer. ✅**
* (b) Drop it; carry only the top-level manifest `schema_version`.

### Fork 5 — `cache_stats` cost fields (`saved_usd_est`, `incurred_usd_est`)

* (a) Include them, populated with `0.0` where no cost model exists.
* **(b) Omit them in v1; re-add additively when a cost model is introduced. ✅**

## Decision Outcome

### Fork 1 — Evolution path: (c) `2.0.0` restructure

The manifest `schema_version` becomes `2.0.0`. The restructure (Forks 2–5) is a single, deliberate
major-version event. **After `2.0.0`, strict-additive discipline resumes within `2.x.x`:** every
subsequent change must add a field with a default or optional marker; no remove, rename, type-change,
restructure, or required/optional flip without a `3.0.0` and a superseding ADR.

### Fork 2 — Evaluation outputs at top level: (b)

`scorecards` and `compile_checks` are top-level keys alongside `artefacts`, reflecting that they are
evaluation outputs rather than pipeline artefacts.

### Fork 3 — Integrity + `--ast-only`: (c) required `sha256` + `llm_skipped` + omit

Every artefact pointer present in the manifest carries a non-null `sha256`. The `--ast-only` run (which
skips the LLM passes and emits no `llm-annotations.json`) is represented two ways, redundantly by
design so the state is unambiguous:

* a top-level `llm_skipped: bool` (always present; `false` on a full run, `true` on `--ast-only`), and
* omission of the `llm_annotations` entry from `artefacts`.

This makes the contract clean: **a pointer present ⇒ the file exists ⇒ its `sha256` is non-null**;
*and* the reason an output is absent is stated explicitly rather than inferred. It also distinguishes
"deliberately skipped" from "expected but missing" (a producer bug), which a bare omission cannot.

### Fork 4 — Retain per-artefact `schema_version`: (a)

Each artefact pointer keeps its own `schema_version`, so a consumer learns an artefact's format version
from the manifest without opening the artefact. This honours the manifest-as-version-authority contract
(ADR-006).

### Fork 5 — Defer cost fields: (b)

`cache_stats` entries carry only `{calls, hits, hit_rate}` in v1. The cost-estimate fields
(`saved_usd_est`, `incurred_usd_est`) require a cost model (a per-model price table) that v1 does not
implement; including them would ship numbers that are structurally present but always `0.0`. They are
re-added as an **additive `2.x` minor bump when a cost model is introduced** (see the constraint flagged
below).

### Canonical schema

```python
# codeograph/manifest/schema.py
from pydantic import BaseModel, ConfigDict, Field

class ArtefactPointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str                                       # POSIX-relative to the manifest's directory
    schema_version: str                             # per-artefact format version (Fork 4)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")  # required (Fork 3)

class ScorecardPointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    overall: str = Field(pattern=r"^(pass|fail|skip|mixed)$")

class CompileChecksPointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

class CacheStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calls: int
    hits: int
    hit_rate: float
    # saved_usd_est / incurred_usd_est deferred until a cost model exists (Fork 5)

class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # scalars
    schema_version: str                             # "2.0.0"
    codeograph_version: str
    source_path: str
    corpus_id: str
    run_id: str                                      # required in 2.0.0 (see Invariants)
    llm_skipped: bool = False                        # Fork 3
    # aggregates
    cache_stats: dict[str, CacheStats] | None = None
    # payload pointers
    artefacts: dict[str, ArtefactPointer] = Field(default_factory=dict)
    scorecards: dict[str, ScorecardPointer] | None = None
    compile_checks: dict[str, CompileChecksPointer] | None = None
```

**Invariants:** `artefacts["graph"]` is always present. `artefacts["llm_annotations"]` is present iff
`llm_skipped` is `false`. Every present pointer's `sha256` is non-null. **`run_id` is required** — every
`2.0.0` manifest is produced by the current tool, which generates `run_id` at pipeline start (ADR-022
Fork 3); its `Optional` typing in `1.x` existed only to tolerate pre-`1.7.0` manifests that predated the
field, and is shed here by the same reasoning that makes `sha256` required.

By contrast, `cache_stats`, `scorecards`, and `compile_checks` remain optional **by design** — they
encode real run states (no LLM passes, no `eval` run, no rendered target, respectively), not legacy
looseness. The major bump tightens *legacy-compat* optionals (`run_id`, `sha256`); it does not blanket-
require fields that have a genuine "did not happen" state.

Full-run and `--ast-only` examples:

```json
{ "schema_version": "2.0.0", "codeograph_version": "0.1.0",
  "source_path": "/…/spring-blog-api", "corpus_id": "spring-blog-api",
  "run_id": "2026-05-30T14-32-11Z-a3f2c8", "llm_skipped": false,
  "cache_stats": { "pass_1": { "calls": 247, "hits": 89, "hit_rate": 0.36 } },
  "artefacts": {
    "graph":           { "path": "graph.json",           "schema_version": "1.0.0", "sha256": "<64hex>" },
    "llm_annotations": { "path": "llm-annotations.json", "schema_version": "1.0.0", "sha256": "<64hex>" } },
  "scorecards":     { "graph": { "path": "evals/graph-scorecard.json", "sha256": "<64hex>", "overall": "pass" } },
  "compile_checks": { "ts":    { "path": "evals/compile-checks.ts.json", "sha256": "<64hex>" } } }
```
```json
{ "schema_version": "2.0.0", "codeograph_version": "0.1.0",
  "source_path": "/…/spring-blog-api", "corpus_id": "spring-blog-api",
  "run_id": "2026-05-30T14-32-11Z-a3f2c8", "llm_skipped": true,
  "artefacts": { "graph": { "path": "graph.json", "schema_version": "1.0.0", "sha256": "<64hex>" } },
  "scorecards": { "graph": { "path": "evals/graph-scorecard.json", "sha256": "<64hex>", "overall": "pass" } } }
```

### Validation discipline

Strict-on-write (`extra="forbid"`); a committed JSON Schema at
`codeograph/_generated/manifest.schema.json` is regenerated from the Pydantic source and pinned by the
CI freshness gate, so external consumers validate independently of the package version.

### Constraint flagged for the future cost-model work (cost-control ADR / ADR-015 amendment)

When a cost model (per-model price table) is introduced, `cache_stats` regains `saved_usd_est` and
`incurred_usd_est` as an **additive `2.x` minor bump** — no major version, no restructure. The owning
ADR (the cost-control CLI ADR, or an amendment that lands the price table) cites this constraint.

## Consequences

**Positive.**
1. Top-level `artefacts` / `scorecards` / `compile_checks` read as the three real output categories.
2. Integrity is a hard contract — every present pointer is hashed; no nullable-`sha256` ambiguity.
3. The `--ast-only` state is explicit (`llm_skipped`) and unambiguous (omission), distinguishing
   "skipped" from "missing."
4. Per-artefact `schema_version` is retained, preserving manifest-as-version-authority.
5. The manifest carries only fields v1 can populate truthfully; cost fields arrive with their model.
6. A single deliberate major bump replaces an unresolvable additive-vs-restructure tension; `2.x`
   evolution is additive and predictable again.

**Negative.**
1. A major bump means a `1.x` reader cannot parse a `2.0.0` manifest. Mitigated: no external consumers
   exist to migrate.
2. Committed example outputs must be refreshed to `2.0.0`.
3. The `llm_skipped` boolean plus the omission convention is two signals for one state — redundant by
   design (for unambiguity), but a contributor must honour both.
4. Splitting evaluation outputs to the top level means a reader scans three keys, not one, to inventory
   a run — accepted in exchange for correct categorisation.

## Confirmation

1. A full run produces a manifest with `schema_version == "2.0.0"`, `llm_skipped == false`, and both
   `artefacts.graph` and `artefacts.llm_annotations` present with non-null `sha256` matching
   `^[0-9a-f]{64}$` (integration test).
2. An `--ast-only` run produces `llm_skipped == true`, **no** `llm_annotations` key under `artefacts`,
   and no `cache_stats` (integration test).
3. Constructing a `Manifest` with any pointer whose `sha256` is `null` or non-64-hex raises
   `ValidationError` (unit test) — there is no nullable-`sha256` path.
4. `scorecards` and `compile_checks` are top-level; a manifest placing them under `artefacts` fails
   JSON-Schema validation (schema-validation test).
5. `artefacts.graph.schema_version` is present and is a string (unit test) — per-artefact version retained.
6. A `CacheStats` carrying `saved_usd_est` or `incurred_usd_est` raises `ValidationError`
   (`extra="forbid"`), confirming cost fields are absent in v1 (unit test).
7. A manifest written by a hypothetical `2.1.0` producer with one added optional field is read
   successfully by the current reader, the unknown field handled per the forward-compat rule
   (fixture test) — additive `2.x` evolution holds.
8. `python -m codeograph.manifest.schema_cli --check` exits 0 on a clean tree and non-zero when the
   Pydantic source changes without regenerating `codeograph/_generated/manifest.schema.json`
   (CI freshness test); the committed schema declares `$schema: 2020-12`.
9. Constructing a `Manifest` without `run_id`, or with `run_id: null`, raises `ValidationError` —
   `run_id` is a required scalar in `2.0.0` (unit test). Conversely, a `Manifest` with `cache_stats`,
   `scorecards`, and `compile_checks` all absent validates successfully (they are optional run states).

## Pros and Cons of the Considered Options

### Fork 1 — Evolution path

**(a) Continue strict-additive `1.x`; keep nested.**
* Good, because no break; existing example outputs unchanged.
* Good, because honours the prior strict-additive intent.
* Bad, because it permanently keeps the mis-categorisation and nullable-`sha256` weaknesses — they
  cannot be fixed additively.
* Bad, because it preserves the unresolved tension (a layout that wants restructuring inside a rule that
  forbids it).

**(b) Additive migration via deprecation cycle.**
* Good, because no hard break at any instant.
* Bad, because it requires both shapes to coexist and a later removal pass — operational overhead for a
  product with a single internal consumer.
* Bad, because the interim manifest carries duplicate/old fields, which is its own readability cost.

**(c) `2.0.0` restructure. ✅ Chosen.**
* Good, because it fixes categorisation and integrity in one deliberate, honest version event.
* Good, because the break is free — no external consumers exist.
* Good, because strict-additive evolution resumes cleanly within `2.x`.
* Bad, because `1.x` readers cannot parse `2.0.0` (no installed base to mind) and example outputs need a
  refresh.

### Fork 2 — Evaluation-output placement

**(a) Nested under `artefacts`.**
* Good, because a reader finds all per-target outputs under one key.
* Bad, because it conflates evaluation outputs with pipeline artefacts — a category error.
* Bad, because schema evolution of either kind disturbs a shared container.

**(b) Top-level peers. ✅ Chosen.**
* Good, because the top-level shape mirrors the real output categories.
* Good, because artefacts and evaluations evolve independently.
* Bad, because inventorying a run reads three keys rather than one (minor).

### Fork 3 — Integrity + `--ast-only`

**(a) Nullable `sha256`.**
* Good, because the simplest representation of "no file."
* Bad, because it weakens integrity to a soft guarantee and overloads `null`.

**(b) Required `sha256` + omit on skip.**
* Good, because a present pointer always means an integrity-checked file.
* Bad, because omission alone cannot distinguish "deliberately skipped" from "a producer bug dropped it."

**(c) Required `sha256` + `llm_skipped` + omit. ✅ Chosen.**
* Good, because integrity stays a hard guarantee.
* Good, because the skipped state is explicit and unambiguous.
* Good, because it distinguishes skipped from missing.
* Bad, because two signals encode one state (redundant by design).

### Fork 4 — Per-artefact `schema_version`

**(a) Retain. ✅ Chosen.**
* Good, because a consumer learns an artefact's format without opening it.
* Good, because it honours manifest-as-version-authority (ADR-006).
* Bad, because it is one more field per pointer (small).

**(b) Drop.**
* Good, because a leaner pointer.
* Bad, because it removes a real forward-compatibility signal and contradicts ADR-006's version-authority
  contract.

### Fork 5 — Cost fields

**(a) Include, `0.0` when no model.**
* Good, because the shape is stable across the cost-model introduction.
* Bad, because it ships numbers that are always `0.0` in v1 — misleading in a shipped artefact.

**(b) Defer. ✅ Chosen.**
* Good, because the manifest states only what v1 can compute truthfully.
* Good, because re-adding the fields is a clean additive `2.x` bump when the model exists.
* Bad, because a future minor bump is required to add them (acceptable; that is normal additive evolution).

## More Information

### Relationships

* **ADR-006** (knowledge graph schema) — its manifest-as-version-authority contract (the manifest holds
  per-artefact `schema_version`; artefact files carry none) is honoured by Fork 4; ADR-006 needs no change.
* **ADR-022** (run manifest + structured logging) — this ADR **partially supersedes** ADR-022: it
  replaces ADR-022's manifest-schema decisions (the evolution rule, the canonical layout, and manifest
  validation). ADR-022's structured-logging decisions (run-id format, dual-emission logging, per-run
  directory layout, log levels) **remain in force.** ADR-022 carries a status note pointing here.
* **ADR-015** (telemetry + response cache) — this ADR supersedes ADR-015's `cache_stats` *shape*: the
  v1 block is `{calls, hits, hit_rate}`. ADR-015 carries an amendment note pointing here.
* **ADR-007** (golden-graph pattern) — the `--ast-only` mode is the trigger for `llm_skipped: true` and
  the omission of the `llm_annotations` pointer.
* **ADR-017** (evaluation framework) — `scorecards` and `compile_checks` are the evaluation outputs now
  promoted to top-level pointers.

### Deferred items

* `cache_stats.saved_usd_est` / `incurred_usd_est` — re-added as an additive `2.x` bump when a cost
  model is introduced (cost-control CLI ADR, or an ADR-015 amendment landing the price table).

### References

* SemVer 2.0.0 — https://semver.org
* JSON Schema 2020-12 — https://json-schema.org/draft/2020-12/schema
* Pydantic v2 — https://docs.pydantic.dev/
