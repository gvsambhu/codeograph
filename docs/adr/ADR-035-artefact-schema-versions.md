---
status: proposed
date: 2026-11-12
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-035 — Artefact Schema Versions

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `7eb02d3` (2026-11-10). ADR text and
code are cited as they stand at that commit.

**NFR-7 AC-1** requires every emitted artefact whose format the tool defines to declare its schema version
*"in the artefact itself and in the manifest, independently per artefact"*. Two decisions placed the
version differently, and the code follows neither consistently.

**ADR-006 Fork 6 chose the manifest as the single source of truth** (option d). Files carry no
`schema_version`; a reader opens the manifest first and dispatches on the versions it declares. Its
reasons: duplicated version metadata can disagree — the *liar risk*, which there was weighed between a
filename and a field — and the manifest is always beside the files. It cited Docker images, npm lockfiles,
OCI artefacts and BIDS datasets. Its Consequences accepted that *"`graph.json` cannot be read
standalone"*. **ADR-025 Fork 4** kept a `schema_version` on each artefact pointer to honour that
contract.

**Three things count against the manifest-only rule.**

1. **The graph is read without its manifest.** It is an output in its own right, for a consumer who never
   renders (FR-2), obtainable on its own (FR-34 AC-4), and validated against its published schema (FR-7b).
   A file handed over alone cannot say what it is.
2. **The project holds two conventions.** The scorecards and the compile-check record were
   designed after ADR-006 and carry `schema_version` in the file (`evals/scorecard.schema.json` requires
   it; `cli/render_pipeline.py:137` writes it) — and their manifest pointers carry none
   (`manifest/models.py:62-87`). The graph and the annotations carry it only on the pointer.
3. **Formats built for other tools carry their version in the document** — SARIF (`version`), CycloneDX
   (`specVersion`), SPDX (`spdxVersion`), OpenAPI (`openapi`); and, of the formats Fork 6 cited, npm's
   lockfile (`lockfileVersion`) and the OCI image manifest (`schemaVersion`). The manifest-only pattern
   fits opaque content a manifest describes — OCI layers, a BIDS dataset's files — which the graph is not.

**What the code does.**

| Artefact | In the file | On its manifest pointer |
|---|---|---|
| `graph.json` | none — the schema's root allows `nodes`, `edges`, `projectOverview` only, and forbids other properties (`schema/graph.schema.json`) | `1.0.0`, from one constant (`graph/graph_writer.py:49,124`) |
| `llm-annotations.json` | none — the file is a bare list (`passes/pass1/node_annotator.py:197`), though its published schema declares an object root with `annotations` only | **the graph's version, copied** (`analyzer/llm_corpus_enricher.py:181`: *"same version as graph in v1"*) |
| scorecards | `schema_version`, required | no field (`ScorecardPointer`) |
| compile-check record | `schema_version` | no field (`CompileChecksPointer`) |

**No reader checks a version.** `render` validates the graph's shape and nothing else
(`cli/render.py:151`), and nothing compares one: the code that handles `schema_version` writes or copies
it. Every check this ADR decides is new code.

The output-layout and evaluation clusters add more artefacts the manifest indexes — the corpus synthesis,
the extraction report, the classpath record, each rendered target's file list, the render audit — each
designed with its own `schema_version` (ADR-029, ADR-033, and the amendments to ADR-025 that accompany ADR-032 and ADR-033).

**The question:** where an artefact's schema version is recorded, what a reader does when it is missing
or two records disagree, and how the versions move.

## Decision Drivers

* **Schema discipline** — one rule for every artefact, not one per ADR.
* **No silent failures** — a disagreement between two records of one fact is an error, never resolved
  by preferring one quietly.
* **Multi-language consumability** — a consumer in any language learns a file's format from the file.
* **Industry-standard pattern** — documents built for other tools to read carry their own version.
* **Least surprise** — a consumer who reads only the manifest still learns every format.

## Considered Options

### Fork 1 — Where an artefact's schema version is recorded

* (a) The manifest only (ADR-006 Fork 6 (d), as decided).
* (b) The file only; the manifest pointer drops the field.
* **(c) A field at the file's root, and a copy on its manifest pointer; the file is the authority. ✅**
* (d) In the file name.

### Fork 2 — A file that carries no version

* **(a) Refused, with ADR-031's refusal status 3 and a message naming the command that re-creates it. ✅**
* (b) Read through its manifest pointer's version, when a manifest is present.
* (c) Migrated in place by adding the field.

### Fork 3 — A file whose version disagrees with its pointer

* **(a) A failure, exit status 1 — a failed precondition, as for an unreadable manifest — naming both
  values. ✅**
* (b) Refused with ADR-031's refusal status 3.
* (c) The file wins, with a warning.

### Fork 4 — Pointers that have no version field

* **(a) The scorecard and compile-check pointers gain an optional `schema_version` — an additive `2.x`
  minor of the manifest. ✅**
* (b) Scorecards and compile-check records move under `artefacts`, as artefact pointers.
* (c) They are exempt.

### Fork 5 — How many major versions a schema takes in one release

* **(a) One per schema per release: every breaking change to a schema released together shares one
  major bump. ✅**
* (b) One per breaking change.

## Decision Outcome

### Fork 1 — Field at the root, copy on the pointer: (c)

**Every artefact the manifest indexes carries `schema_version` at its root**: the graph, the
annotations, the corpus synthesis, the extraction report, the classpath record, each rendered target's
file list, the compile-check record, the render audit and the scorecards.

* **The writer writes the file and its pointer from one constant**, so the two cannot be produced
  different.
* **The pointer keeps its copy** (ADR-025 Fork 4), so a consumer still learns every format from the
  manifest without opening a file. The file is the authority; the pointer indexes it.
* **Each schema has its own version line.** The annotations stop borrowing the graph's version; their
  line starts at the version their next release gives them (Fork 5).
* **The rendered source carries none** — its format is the target stack's. Its file list carries its own
  `schema_version`.
* **Diagnostic records are not indexed.** The telemetry records and the invocation history version
  their own entries (ADR-015, ADR-030); the log format is ADR-022's.
* **The annotations file's envelope** — `{ "graph_ref": …, "annotations": { … } }` (ADR-006, the
  evaluation cluster's amendment) — gains `schema_version` beside `graph_ref`.

Fork 6's *liar risk* was two records that could disagree with nothing to notice. Here they are written
from one constant and compared on every read (Fork 3), so a disagreement cannot pass silently.

### Fork 2 — A file with no version is refused: (a)

A file the tool defines that has no `schema_version` at its root was written before this ADR, or by
something else. **It is refused with ADR-031's refusal status 3** — nothing changed, as for an
earlier-version folder, which ADR-031 lists under the same status — and the message names the file and
the command that re-creates it. No fallback reads it through the manifest.

* **Which files this meets.** A run directory in the layout before ADR-029's is refused before any file
  is read, by ADR-028 Fork 3's shape test. This fork covers what that test does not catch, both reached
  only if this ADR ships in a later release than ADR-029's layout:
  - a run directory in ADR-029's layout written by a release before this ADR — it has an invocation
    history, so the shape test passes it;
  - a file copied into a run directory from one of those.
* **Re-creating it is cheap**: the graph is byte-identical for the same corpus and recorded extraction
  settings (NFR-6), and every LLM result returns from the response cache (FR-17). ADR-026 makes no
  compatibility promise before `1.0.0`.

### Fork 3 — A disagreement is a failure: (a)

A reader that finds a file's `schema_version` different from its pointer's **fails with exit
status 1**, naming the file, both values and the command that re-creates it. Neither value
overrides the other.

**A failure, not a refusal.** ADR-031's status 1 covers a precondition the run directory does not meet,
such as an unreadable manifest; a manifest that contradicts its own files is the same kind of fault. It is
not the version of a release the user can re-run past, as a missing version is (Fork 2): a crash between
writing a file and writing the manifest is recovered by ADR-028 Fork 5's journal, so a disagreement that persists after a
recovery means something outside the tool changed a file. A read that races a publish, or follows a crash
whose recovery waits for `--break-lock`, can meet one before then.

### Fork 4 — The two pointers gain the field: (a)

`ScorecardPointer` and `CompileChecksPointer` gain an optional `schema_version`, written from the same
constant as their files. Adding an optional field is additive within `2.x` (ADR-025's evolution rule): the
manifest takes a minor version, merged with the release's other manifest change. The field is optional
only so that `2.x` readers keep working; the tool always writes it.

### Fork 5 — One major per schema per release: (a)

A schema whose release carries several breaking changes takes **one** major bump. Adding a root
property to the graph or the annotations is breaking — both schemas forbid unknown root properties — so
each takes a major version (NFR-7 AC-3). The graph's shares its major with the other breaking changes
to its schema released with it: the `projectOverview` removal and the extraction-mode vocabulary change
(ADR-006). The annotations' shares its major with the envelope change and the record changes of the
evaluation cluster's ADR-006 amendment. **This fork owns the rule.** ADR-032's *Constraint flagged for
ADR-026* applies it to the graph, annotations and manifest schemas of the release it ships in.

### What this changes in other ADRs

**Proposed ADRs, conformed with this one** (edited in place, with a Revision-history line):
* **ADR-029** Fork 6 — render's two records carry `schema_version` at their root, copied on their
  pointers.
* **ADR-033** Forks 3 and 5 — the classpath record and the extraction report likewise.
* **ADR-032** *Constraint flagged for ADR-026* — cites Fork 5 here for the one-bump rule it applies.

#### Constraint flagged for ADR-006
On acceptance, **Fork 6 (d) is superseded** by Fork 1 here, with its Consequence *"`graph.json` cannot be
read standalone"*; the graph and annotations schemas each gain a required root `schema_version`.

#### Constraint flagged for ADR-025
On acceptance, **Fork 4's version-authority clause is superseded**: the pointer copies the file's version
rather than being its only record. Fork 4 itself stands. `ScorecardPointer` and `CompileChecksPointer`
gain an optional `schema_version` (Fork 4 here), in the next `2.x` minor.

#### Constraint flagged for ADR-007
Adding the field changes every golden's bytes: one refresh under the `change` category, citing this ADR.

#### Constraint flagged for ADR-026
At the release that ships this: the graph schema and the annotations schema each take one major version,
shared with the other breaking changes released with them; the manifest takes one `2.x` minor (Fork 5).

#### Constraint flagged for ADR-031
A file with no version is refused with status 3, beside *an earlier-version folder* (Fork 2). A file
whose version disagrees with its pointer exits with status 1, beside *an unreadable manifest* (Fork 3).

## Consequences

**Positive.**
1. Every artefact describes itself; a file met on its own can be validated and dispatched.
2. One rule covers every artefact; the project's two conventions become one.
3. A disagreement between a file and its pointer is caught on every read.
4. The annotations get their own version line, so a change to one schema does not move the other's
   number.

**Negative.**
1. The graph and the annotations each take a major version, and every golden is refreshed.
2. A file written by `0.5.0` cannot be read by the release that ships this; it is re-created.
3. Each reader gains a version check, and each writer a second place it writes the version.
4. The manifest's copy is redundant by design; keeping it costs a comparison on every read.

## Confirmation

1. After `run`, `render` and `eval`, every artefact the manifest indexes holds a root `schema_version`
   equal to its pointer's (integration test).
2. A file whose `schema_version` differs from its pointer fails with exit status 1, naming the file
   and both values, and nothing is written (unit test).
3. A run directory whose `analysis/graph.json` has no `schema_version` is refused by `render` with
   status 3 and a message naming the command that re-creates it, and nothing is written (integration
   test).
4. `llm-annotations.json` validates against its published schema, which requires `schema_version`,
   `graph_ref` and `annotations` (integration test — FR-7b AC-1).
5. Changing the graph's schema-version constant leaves the annotations' version unchanged (unit test).
6. Every scorecard and compile-check pointer carries `schema_version`, equal to its file's (unit test).
7. Each artefact's data model declares `schema_version`; a file without it is refused with status 3 and
   the message of Fork 2, not a generic validation error (unit test).
8. Changing the graph's `schema_version` leaves every LLM response-cache key unchanged (unit test).
9. The golden refresh that adds the field is logged under the `change` category, citing this ADR (review
   check on the refresh).

## Pros and Cons of the Considered Options

### Fork 1 — Where the version is recorded

**(c) Field at the root, copy on the pointer. ✅ Chosen.**
* Good, because a file met on its own says what it is.
* Good, because a consumer still learns every format from the manifest alone.
* Good, because one constant writes both, and every read compares them.
* Bad, because the version is stored twice, and the copy must be kept equal.

**(a) The manifest only.**
* Good, because the version is stored once.
* Good, because file names and file contents are unchanged.
* Bad, because a file without its manifest cannot be identified, and NFR-7 AC-1 is not met.

**(b) The file only.**
* Good, because the version is stored once, where the content is.
* Good, because a file met on its own says what it is.
* Bad, because a consumer must open every file to learn the formats, which ADR-025 Fork 4 kept the
  pointer to avoid, and NFR-7 AC-1 asks for the manifest too.

**(d) In the file name.**
* Good, because the version is visible without opening anything.
* Good, because two versions can sit side by side.
* Bad, because every path that names an artefact changes with each major version, and the name and any
  field can still disagree.

### Fork 2 — A file with no version

**(a) Refused. ✅ Chosen.**
* Good, because there is one way to read a file, with no legacy path to keep working.
* Good, because it takes the status ADR-031 gives an earlier-version folder, so one condition has one
  status.
* Good, because re-creating a file is cheap — the graph is deterministic and LLM results are cached.
* Bad, because a user holding an older file must re-run to read it.

**(b) Read through the manifest pointer.**
* Good, because older run directories keep working.
* Good, because nothing is re-run.
* Bad, because a second read path is kept and tested, and a file met on its own still cannot be read.

**(c) Migrated in place.**
* Good, because older files become current.
* Good, because the user does nothing.
* Bad, because migration code is kept in the tool, which ADR-028 Fork 3 decided against, and a file is
  rewritten that its hash records.

### Fork 3 — A disagreement

**(a) A failure, status 1. ✅ Chosen.**
* Good, because an inconsistent run directory is reported as a failed precondition, as ADR-031 reports
  an unreadable manifest.
* Good, because neither record silently wins.
* Bad, because a user must re-create the run directory to proceed.

**(b) Refused, status 3.**
* Good, because it reuses ADR-031's refusal path.
* Good, because nothing is written, as for any refusal.
* Bad, because status 3 says the directory is in a state the user can act on and re-run, and here the
  directory itself contradicts its record — the same class as an unreadable manifest, which ADR-031
  gives status 1.

**(c) The file wins, with a warning.**
* Good, because work continues.
* Good, because the file is the authority by Fork 1.
* Bad, because a changed file is read as if nothing were wrong, and a warning in CI goes unread.

### Fork 4 — Pointers without a field

**(a) Both pointers gain an optional field. ✅ Chosen.**
* Good, because it is additive within `2.x`.
* Good, because NFR-7 AC-1 is met for both.
* Bad, because the field is optional in the schema though always written.

**(b) Move them under `artefacts`.**
* Good, because every indexed file then has one pointer shape.
* Good, because the version field comes with it.
* Bad, because it restructures the manifest against ADR-025 Fork 2's grouping, and breaks `2.x` readers.

**(c) Exempt them.**
* Good, because nothing changes.
* Good, because their files carry the version.
* Bad, because NFR-7 AC-1 is not met for them.

### Fork 5 — Majors per release

**(a) One per schema per release. ✅ Chosen.**
* Good, because a consumer migrates once per schema per release.
* Good, because the number says how many incompatible lines exist, not how many changes made them.
* Bad, because one major can carry several unrelated breaking changes, which the changelog must list.

**(b) One per breaking change.**
* Good, because each break is visible in the number.
* Good, because a change is traced to its bump.
* Bad, because a consumer sees several majors in one release, with no version in between ever shipped.

## More Information

### Relationships

* **ADR-006** (knowledge graph schema) — on acceptance, **Fork 6 (d) is superseded** by Fork 1.
* **ADR-025** (manifest schema) — on acceptance, Fork 4's version-authority clause is superseded; two
  pointers gain a field (Fork 4).
* **ADR-017** (evaluation framework) — the scorecards carry their version in the file; this rule
  covers them by name.
* **ADR-028** (what a command may overwrite, delete or refuse) — Fork 3 refuses earlier-version run
  directories; Fork 5's recovery runs before any version is read.
* **ADR-029** (output layout and ownership) and **ADR-033** (extraction environment and parser failures)
  — their records follow this rule.
* **ADR-031** (command outcomes and consent) — a missing version takes status 3, a mismatch status 1.
* **ADR-032** (evaluation semantics) — its constraint for ADR-026 applies Fork 5's rule.
* **ADR-026** (release version management) — schema versions are separate from the application version
  (NFR-7 AC-2); the release applies Fork 5.
* **ADR-007** (golden-graph pattern) — one `change` refresh.

### Requirements touched

* **NFR-7 AC-1** — every artefact declares its version in the file and in the manifest (Forks 1, 4).
* **NFR-7 AC-3** — a breaking change starts a new major line, one per schema per release (Fork 5).
* **FR-2, FR-34 AC-4** — the graph is usable on its own (Fork 1).
* **FR-7b AC-1** — every emitted graph and enrichment file validates against its published schema,
  which requires the field (Fork 1).

### References

* Requirements — `docs/requirements.md` (NFR-7, FR-2, FR-7b, FR-34).
* SARIF 2.1.0 — `version` property.
* CycloneDX — `specVersion`.
* SPDX — `spdxVersion`.
* OpenAPI — `openapi` field.
* npm — `package-lock.json` `lockfileVersion`.
* OCI image manifest — `schemaVersion`.

### Deferred

* None.

### Open questions

* None.
