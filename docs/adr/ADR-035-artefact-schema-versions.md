---
status: proposed
date: 2026-11-19
decision-makers: gvsambhu
consulted: AI design advisor
informed: future contributors
---

# ADR-035 — Artefact Schema Versions

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0 (2026-11-10).

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
2. **The project holds two conventions.** The scorecards and the compile-check record were designed after
   ADR-006 and carry `schema_version` in the file, while their manifest pointers carry none; the graph and
   the annotations carry it only on the pointer (table below).
3. **Formats built for other tools carry their version in the document** — SARIF (`version`), CycloneDX
   (`specVersion`), SPDX (`spdxVersion`), OpenAPI (`openapi`); and, of the formats Fork 6 cited, npm's
   lockfile (`lockfileVersion`) and the OCI image manifest (`schemaVersion`). The manifest-only pattern
   fits opaque content a manifest describes — OCI layers, a BIDS dataset's files — which the graph is not.

**What the code does.**

| Artefact | In the file | On its manifest pointer |
|---|---|---|
| `graph.json` | none — the published schema's root allows `nodes`, `edges`, `projectOverview` only, and forbids other properties | `1.0.0`, from one constant in the graph writer |
| `llm-annotations.json` | none — the file is a bare list, though its published schema declares an object root with `annotations` only | **the graph's version, copied** — the code treats the two as one version in v1 |
| scorecards | `schema_version`, required by their published schema and written by the evaluator | no field (`ScorecardPointer`) |
| compile-check record | `schema_version`, written by `render` | no field (`CompileChecksPointer`) |

**No reader checks a version.** `render` validates the graph's shape and nothing else, and nothing
compares one: the code that handles `schema_version` writes or copies it. Every check this ADR decides is
new code.

The output-layout and evaluation clusters add more artefacts the manifest indexes, each designed with its
own `schema_version`: the corpus synthesis and each rendered target's file list (ADR-029, with the
amendment to ADR-025 that accompanies it), the render audit (the amendment to ADR-010 that accompanies
ADR-029), and the extraction report and the classpath record (ADR-033). The amendments these clusters make
to accepted ADRs are held until the clusters are accepted, and merge with them.

**The question:** where an artefact's schema version is recorded; what a reader does with a file whose
version it does not read — missing, or present but not one it reads — and with two records of one version
that disagree; and how the versions move.

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

### Fork 2 — A file in a version the reader does not read

* **(a) Refused with ADR-031's refusal status 3 — a file with no version, or at a major the reader does
  not read, older or newer — with a message naming the file, its version, the versions the tool reads
  and the remedy. ✅**
* (b) A file with no version is read through its manifest pointer's version, when a manifest is present.
* (c) A file with no version is migrated in place by adding the field.
* (d) As (a), but a newer major is a failure, exit status 1.

### Fork 3 — A file whose hash verifies but whose version disagrees with its pointer

* **(a) A failure, exit status 1 — a failed precondition, as for an unreadable manifest — naming both
  values. ✅**
* (b) Refused with ADR-031's refusal status 3.
* (c) The file wins, with a warning.

### Fork 4 — Pointers that have no version field

* **(a) The scorecard and compile-check pointers gain an optional `schema_version` — an additive `2.x`
  minor of the manifest. ✅**
* (b) Scorecards and compile-check records move under `artefacts`, as artefact pointers.
* (c) They are exempt.

### Fork 5 — How many version bumps a schema takes in one release

* **(a) One per schema per release, major or minor: the breaking changes released together share one
  major, the additive changes one minor. ✅**
* (b) One per change.

## Decision Outcome

### Fork 1 — Field at the root, copy on the pointer: (c)

**Every artefact the manifest indexes carries `schema_version` at its root**: the graph, the
annotations, the corpus synthesis, the extraction report, the classpath record, each rendered target's
file list, the compile-check record, the render audit and the scorecards.

* **The writer writes the file and its pointer from one constant**, so the two cannot be produced
  different.
* **The pointer keeps its copy** (ADR-025 Fork 4), so a consumer still learns every format from the
  manifest without opening a file. The file is the authority; the pointer indexes it.
* **Each schema has its own version line.** The annotations stop borrowing the graph's version. Their
  line continues from the `1.0.0` their pointer carried, so the release that ships this gives them
  `2.0.0` (Fork 5); from then on the two lines move independently.
* **One published schema per major.** Each published JSON Schema names its major in its `$id`, and pins
  `schema_version` to that major exactly, with the minor and patch matched by a pattern
  (`^2\.\d+\.\d+$` for a `2` major), so validating a file tells a consumer which major it is. Within a
  major the schema grows by its minors in place. The writer's constant holds the full version — the minor
  and patch are authored there, once — and CI checks that it is in the major its schema names, as
  ADR-022's freshness gate checks the manifest's schema, and that it equals the newest entry of the
  schema's version log, so a minor is never added without its log line. The patch is `0` until an ADR
  defines a patch release; the pattern admits one for that day. When a schema takes a new major, the
  schema of each earlier released major stays committed beside it, so a consumer pinned to it can still
  validate (FR-7b AC-3); each schema keeps a version log, as the manifest does
  (`docs/manifest-versions.md`), recording what each minor added.
* **The rendered source carries none** — its format is the target stack's. Its file list carries its own
  `schema_version`.
* **Diagnostic records are not indexed.** The telemetry records and the invocation history version
  their own entries (ADR-015, ADR-030); the log format is ADR-022's.
* **Tool-internal state is outside this rule.** The claims, the brief lock and the recovery journal in
  `.locks/` (ADR-028) are neither artefacts nor diagnostic records; their format is ADR-028's, which
  versions the journal (*What this changes in other ADRs*, below).
* **The annotations file's envelope** — `{ "graph_ref": …, "annotations": { … } }`, from the amendment to
  ADR-006 that accompanies ADR-032 and ADR-033 — gains `schema_version` beside `graph_ref`.

Fork 6's *liar risk* was two records that could disagree with nothing to notice. Here they are written
from one constant and compared on every read (Fork 3), so a disagreement cannot pass silently.

### Fork 2 — A version the reader does not read is refused: (a)

**A reader reads exactly the majors it declares** — in v1, one per schema. A file whose `schema_version`
is not one of them is **refused with ADR-031's refusal status 3** — nothing changed, as for an
earlier-version folder, which ADR-031 lists under the same status. No fallback reads it through the
manifest, and no migration rewrites it. The cases:

* **No version** — a file written by a release before this ADR. The message names the file and the
  command that re-creates it.
* **An older major** — a file written by an earlier release. The message names the file, its version, the
  versions the tool reads, and the command that re-creates it.
* **A newer major** — a file written by a later release than the tool reading it. The message names the
  file, its version, the versions the tool reads, and that a release of the tool that reads it is needed.

**A newer minor within a major the reader declares is read** — Fork 5 makes every addition within a
major one a reader can ignore.

**A file list in a version the tool does not read is treated as no file list**, not refused, since the
command that would re-create it is the one reading it. `run` marks the rendered project stale and
proceeds. `render` meets ADR-028 Fork 2's *content but no file list* case, and its refusal names the
`--on-existing` choices that proceed, `overwrite-edited` and `clean`.

**The manifest's own version** follows the same rule: a manifest at a major the tool does not read is
refused with status 3.

* **Which no-version files this meets.** A run directory in the layout before ADR-029's is refused before
  any file is read, by ADR-028 Fork 3's shape test. This fork covers what that test does not catch, both
  reached only if this ADR ships in a later release than ADR-029's layout:
  - a run directory in ADR-029's layout written by a release before this ADR — it has an invocation
    history, so the shape test passes it;
  - a file copied into a run directory from one of those.
* **Re-creating a file is cheap when the release leaves the LLM inputs unchanged.** The graph is
  deterministic for the same corpus, tool version and recorded extraction settings within the declared
  execution envelope (NFR-6). LLM results return from the response cache (FR-17) when the release leaves
  the prompts, the rendered inputs and the output schemas unchanged; a release that changes any of them
  re-pays those calls (Consequences). ADR-026 makes no compatibility promise before `1.0.0`.

### Fork 3 — A disagreement is a failure: (a)

A reader that finds a file's `schema_version` different from its pointer's, **for a file whose hash
matches its pointer**, **fails with exit status 1**, naming the file and both values. Neither value
overrides the other. A manifest that contradicts a file it hashed is the same kind of fault as ADR-031's
unreadable manifest — a precondition the run directory does not meet. The message names the command that
re-creates the run directory.

**The hash is checked first.** A file whose SHA-256 differs from its pointer has changed since the
manifest recorded it; that event already has decided outcomes. Where the reading ADR decides one, it applies:
the check that reads the file is skipped with its reason (the ADR-017 and ADR-032 skips in the read-path table
below), and `eval` completes. A reader with no decided rule for it fails with
status 1, as for a disagreement. The version comparison therefore runs only on files whose hash verifies.

**A publish in progress.** A read that races a publish, or follows a crash whose recovery waits for
`--break-lock`, can meet a changed file or a manifest not yet written. When a recovery journal is present
(ADR-028 Fork 5), the status-1 message names the journal and its owner, and says to retry once that
invocation ends or after `--break-lock` — not to re-create.

### The read path

**One loader verifies every indexed file a command reads**, so the rule is implemented once. It runs in
ADR-028's step 1 — refusal checks and claims — before anything is produced, so a refusal or a failure
there changes nothing (FR-45 AC-2); a command that publishes nothing runs it before it writes anything.
It opens only the files the command reads, so a command never refuses because of a file it does not
read.

For each file, in order:
1. **hash** — the file against its pointer's SHA-256 (Fork 3: the reading ADR's rule, or status 1);
2. **version present** — at the file's root (Fork 2: status 3);
3. **version read** — a major the tool declares (Fork 2: status 3; a file list: treated as none);
4. **agreement** — the file's version against its pointer's copy, when the pointer has one (Fork 3:
   status 1; Fork 4: a pointer with no copy).

A file whose step yields an outcome — a skip, a refusal or a failure — is not examined further: a file
whose hash differs is never checked for a version. The manifest is read first; it has no pointer, so only
steps 2 and 3 apply to it.

| Command | Indexed files it reads | Hash differs | Step of ADR-028 |
|---|---|---|---|
| `run` | each rendered target's file list, for its input fingerprints; one in a version it does not read is treated as none, and the project marked stale. **The graph and annotations it supersedes are archived unread**, so `run` over a run directory written before this ADR re-creates it in place | status 1 | 1 |
| `render` | the graph, the annotations, the target's file list (ADR-028 Fork 2); a file list in a version it does not read is treated as none | status 1 | 1 |
| `eval` | the graph, the annotations, the compile-check record, the render audit, the classpath record | graph — ADR-032's `reproducibility` skip; annotations — ADR-032's `annotations_modified_since_run` skip, and rule 5 of `internal_consistency` not run; compile-check record — ADR-017's skip; render audit — ADR-032's skip; classpath record — ADR-032's `resolution_settings_changed` skip | 1 |
| `eval report` | the scorecards of each run directory it reads | status 1 | before it writes anything (it publishes nothing) |
| `history`, `purge` | none | — | — |

### Fork 4 — The two pointers gain the field: (a)

`ScorecardPointer` and `CompileChecksPointer` gain an optional `schema_version`, written from the same
constant as their files. Adding an optional field is additive within `2.x` (ADR-025's evolution rule): the
manifest takes a minor version, merged with the release's other manifest change. The tool always writes
it; it is optional because a manifest written before this ADR has pointers without it, and that manifest
stays valid.

* **A pointer with no copy** is read on its file's version alone — the file is the authority (Fork 1).
  `eval report` over a run directory written before this ADR reads its scorecards that way.
* **A pointer carried forward** — one a manifest rewrite keeps from an earlier invocation, as
  `render --target go` keeps `ts`'s compile-check pointer — keeps what it had. One with no copy stays
  without until the invocation that owns it rewrites it; no command opens a file it does not read to
  fill it.

### Fork 5 — One bump per schema per release: (a)

**A schema takes at most one version bump per release.** The breaking changes released together share
one major; the additive changes share one minor; a release with both takes the major only. **This fork
owns the rule**; ADR-026 applies it at every release.

**What counts as additive — one rule for every schema.** Within a major, a reader is tolerant: it ignores
properties it does not know, and values of an optional enum it does not know. An **addition** — an
optional property, or a new value of an enum on an optional property — is therefore a **minor**. A
**removal, rename, change of type or change of meaning** is a **major**, and so are **a new required
property**, **a new value of an enum on a required property**, and **a new node or edge kind** in the graph
(a new definition under the schema's `oneOf` on `kind`) — a record cannot be validated or understood
without them. *Required* is judged on the property in its own object: an array of enum items follows its
array, so a new Java modifier is a major, and a required enum inside an optional object is a major.
Because a schema grows only by optional additions, a file at any earlier minor of the major stays valid
against the schema of its major as the schema grows in place.

**Validation follows the same split.** A writer validates strictly against the closed schema of its own
version (FR-7b AC-1). A reader, and the schema-validity checks — ADR-017's for the graph, ADR-032's
`annotations_schema_validity` — validate a file against the published schema of the file's major, with
the properties, and the values of optional enums, that schema does not list ignored. **The mechanism:**
before validating, they drop the properties the major's schema does not list, and any optional property
whose enum value it does not list, then validate what remains against the same closed schema — there is
one published schema per major, and no second, open form. This is the rule the manifest already
follows: strict on write, tolerant on read (ADR-022, ADR-025).

**For an external consumer** (FR-7b AC-3), the published schema is the writer's contract, and it is
strict: validated against the schema of an earlier minor, a file from a later minor may fail it. To read
newer minors, a consumer ignores the properties, and the values of optional enums, that it does not
know — as the tool does — or updates to the latest schema of the major. The schema's version log says
what each minor added.

**At the release that ships this:** the graph's schema breaks — the `projectOverview` removal and the
extraction-mode vocabulary change (ADR-006) — and takes one major, which also carries its new
`schema_version`. The annotations' schema breaks — the envelope change and the record changes of the
amendment to ADR-006 that accompanies ADR-032 and ADR-033 — and takes one major, `2.0.0` (Fork 1).
ADR-032's *Constraint flagged for ADR-026* applies the rule to the release it ships in.

### What this changes in other ADRs

**Proposed ADRs, conformed with this one** (edited in place, with a Revision-history line):
* **ADR-029** Fork 6 — render's two records carry `schema_version` at their root, copied on their
  pointers.
* **ADR-033** Forks 3 and 5 — the classpath record and the extraction report likewise.
* **ADR-032** *Constraint flagged for ADR-026* — cites Fork 5 here for the one-bump rule it applies, and
  the render audit starts at `1.0.0` when it ships with the output-layout cluster. Forks 3, 4 and 6 — an
  annotations file or classpath record whose hash differs skips, as the graph and the render audit do, and
  `annotations_schema_validity` validates against the file's major.
* **ADR-031** Fork 1 — its status table lists the conditions of Forks 2 and 3 among its examples.
* **ADR-028** Fork 5 — the recovery journal carries a format version; one in a version the tool does not
  read is treated as a journal from another process-id space. Forks 3 and 5 state the cache claim's
  condition, as Fork 2 here does.

**Accepted ADRs:**

#### Constraint flagged for ADR-006
On acceptance, these statements are superseded by Forks 1 and 2 here:
* **Fork 6 (d)** — the Considered Option and its Decision Outcome (*files carry no `schema_version`*;
  *"read manifest first, then dispatch on declared schema versions"*);
* **Fork 7 (c)** — the Considered Option's *"schema bumps tracked in the manifest"*, and its Decision
  Outcome's *"tracked in the manifest"* and *"ADR-022 readers route per-artefact based on the manifest's
  declared versions"*: a bump is recorded in the file and copied on its pointer;
* **Orchestration constraint flagged for ADR-022** — *"assumes `manifest.json` … is authoritative"*: the
  file is the authority;
* **Consequence** *"`graph.json` cannot be read standalone"*;
* **Pros and Cons, Fork 6 (d)** — *"single source of truth, no duplication"*, *"matches Docker / npm /
  OCI / BIDS handling"* and *"individual files cannot be read standalone — manifest is mandatory"*;
* **Confirmations 5 and 6** — the renderer *"dispatches per declared schema version"* through the
  manifest, and *"manifest-driven dispatch"*: succeeded by Confirmation 5 here;
* **Pros and Cons, Fork 7 (c)** — *"manifest already supports independent per-artefact versioning"*;
* **Relationships, ADR-010** — the renderer *"loads `manifest.json` and dispatches per declared schema
  version"*.

The graph and annotations schemas each gain a required root `schema_version` (Fork 1). The 2026-06-17
amendment's closed objects and closed enums hold for write-time validation against the schema of the
file's major; reading within a major follows Fork 5.

#### Constraint flagged for ADR-025
On acceptance, these statements of the manifest-as-version-authority contract are superseded: the pointer
copies the file's version rather than being its only record.
* **Context** — *"Consumers read it first and dispatch on its declared versions"*;
* **Fork 4's Decision Outcome** — *"honours the manifest-as-version-authority contract"*; Fork 4 itself
  stands;
* **Consequence 4** — *"preserving manifest-as-version-authority"*;
* **Pros and Cons, Fork 4** — option (a)'s *"honours manifest-as-version-authority"* and option (b)'s
  *"contradicts ADR-006's version-authority"*;
* **Relationships, ADR-006** — *"artefact files carry none … ADR-006 needs no change"*.

Confirmation 5 (the graph pointer's `schema_version` is present) stands. The two pointers of Fork 4 gain
the field in the next `2.x` minor.

#### Constraint flagged for ADR-007
Adding the field changes every golden's bytes: one refresh under the `change` category, citing this ADR.

#### Constraint flagged for ADR-017
On acceptance, the graph's `schema_validity` check — *"`graph.json` validates against
`codeograph/schema/graph.schema.json`"* — reads as validation against the published schema of the file's
own major, as Fork 5 decides: a file at a newer minor of that major passes. Write-time validation stays
strict (FR-7b AC-1).

#### Constraint flagged for ADR-026
At every release, ADR-026 applies Fork 5's rule. At the release that ships this, the graph schema and the
annotations schema each take one major version, shared with the other breaking changes released with
them; the manifest takes one `2.x` minor (Fork 4).

## Consequences

**Positive.**
1. Every artefact describes itself; a file met on its own can be validated, and a reader knows whether it
   reads it.
2. One rule covers every artefact; the project's two conventions become one.
3. A disagreement between a file and its pointer is caught on every read.
4. The annotations get their own version line, so a change to one schema does not move the other's
   number.
5. Within a major, an addition does not break an existing reader, for every schema.

**Negative.**
1. The graph and the annotations each take a major version, and every golden is refreshed.
2. A file written by `0.5.0` cannot be read by the release that ships this; it is re-created. The
   committed example runs are therefore regenerated in the change that ships this, beside the golden
   refresh. In v1 a tool reads one major per schema, so every later major forces the same re-creation,
   and a newer file needs a newer tool. For a rendered project, a later major of its file list forces an
   `--on-existing` choice instead (Fork 2): its edits can no longer be classified, so `overwrite-edited`
   or `clean` archives them.
3. A release that changes a prompt, a rendered input or an output schema re-pays the LLM calls of every
   run it re-creates; ADR-027's cost gate estimates them.
4. One loader gains the checks, and each writer a second place it writes the version.
5. The manifest's copy is redundant by design; keeping it costs a comparison on every read.
6. Each schema keeps its earlier majors committed and a version log.

## Confirmation

1. After `run`, `render` and `eval`, every artefact the manifest indexes holds a root `schema_version`
   equal to its pointer's (integration test).
2. A file whose SHA-256 matches its pointer but whose `schema_version` differs fails with exit status 1,
   naming the file and both values, and nothing is written; with another invocation's recovery journal
   present, the message names the journal and its owner instead of a re-creating command (unit test).
3. A compile-check record, render audit, annotations file or classpath record changed after it was
   written — its `schema_version` included, or removed — or an annotations file deleted, makes `eval`
   skip the check that reads it with ADR-017's or ADR-032's reason — for the annotations,
   `annotations_schema_validity` skips and rule 5 of `internal_consistency` is not run — and complete,
   not exit with status 1 or 3 (integration test).
4. A run directory whose `analysis/graph.json` has no `schema_version` is refused by `render` with
   status 3 and a message naming the command that re-creates it, and nothing is written (integration
   test).
5. A graph at a major the tool does not read — older or newer — is refused with status 3 and a message
   naming the file, its version and the versions the tool reads, not a validation error (unit test).
6. A file at a newer minor of a major the tool reads, carrying a property and a value of an optional enum
   the reader does not know, is read and passes the schema-validity checks, the unknown ones ignored; a
   file carrying a value of a required enum the schema does not list fails them (unit test).
7. `run` over a run directory written before this ADR succeeds and archives the earlier graph and
   annotations. A file list in a major the tool does not read leaves `run` marking the project stale and
   proceeding, and `render`'s refusal naming `overwrite-edited` and `clean` (integration test).
8. `llm-annotations.json` validates against the published schema of its major, which requires
   `schema_version`, `graph_ref` and `annotations`; a file in another major fails that validation, and a
   writer's file carrying a property the schema does not list fails write-time validation (integration
   test — FR-7b AC-1).
9. Each schema's writer constant is in the major its published schema names and equals the newest entry
   of its version log (CI check).
10. Changing the graph's schema-version constant leaves the annotations' version unchanged (unit test).
11. Every scorecard and compile-check pointer an invocation writes carries `schema_version`, equal to its
    file's; a pointer it carries forward, as `ts`'s after `render --target ts` then `render --target go`,
    keeps what it had, and its file is not opened (unit test).
12. `eval report` over a run directory whose scorecard pointers have no `schema_version` reads each
    scorecard on its file's version (integration test).
13. Each artefact's data model declares `schema_version`; a file without it is refused with status 3 and
    the message of Fork 2, not a generic validation error (unit test).
14. Changing the graph's `schema_version` leaves every LLM response-cache key unchanged (unit test).
15. The golden refresh that adds the field is logged under the `change` category, citing this ADR (review
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

### Fork 2 — A version the reader does not read

**(a) Refused, status 3. ✅ Chosen.**
* Good, because there is one way to read a file, with no legacy path to keep working.
* Good, because it takes the status ADR-031 gives an earlier-version folder, so one condition has one
  status, whichever direction the versions differ in.
* Good, because re-creating a file is cheap when the release leaves the LLM inputs unchanged — the graph
  is deterministic and LLM results are cached.
* Bad, because a user holding an older file must re-run to read it.
* Bad, because a newer file read by an older tool is not fixed by a retry; the message must say a newer
  tool is needed.

**(b) Read through the manifest pointer.**
* Good, because older run directories keep working.
* Good, because nothing is re-run.
* Bad, because a second read path is kept and tested, and a file met on its own still cannot be read.
* Bad, because it covers only a missing version; a present version the reader does not read still needs
  a rule.

**(c) Migrated in place.**
* Good, because older files become current.
* Good, because the user does nothing.
* Bad, because migration code is kept in the tool, which ADR-028 Fork 3 decided against, and a file is
  rewritten that its hash records.

**(d) As (a), but a newer major is status 1.**
* Good, because it says the tool, not the run directory, is out of step.
* Good, because status 1's *precondition not met* describes an installed tool too old for its input.
* Bad, because one condition — a version the tool does not read — takes two statuses depending on
  direction, and ADR-031 lists an earlier-version folder under status 3.

### Fork 3 — A disagreement

**(a) A failure, status 1. ✅ Chosen.**
* Good, because a manifest contradicting a file it hashed is reported as a failed precondition, as
  ADR-031 reports an unreadable manifest.
* Good, because neither record silently wins.
* Good, because checking the hash first leaves ADR-017's and ADR-032's skips for a changed file as they
  were decided.
* Bad, because a user must re-create the run directory to proceed.

**(b) Refused, status 3.**
* Good, because it reuses ADR-031's refusal path.
* Good, because nothing is written, as for any refusal.
* Bad, because ADR-031's status 3 means *refused — nothing changed; safe to retry*, with examples that
  are states a run directory is in, such as an earlier-version folder; a run directory contradicting its
  own record is its status-1 example, an unreadable manifest.

**(c) The file wins, with a warning.**
* Good, because work continues.
* Good, because the file is the authority by Fork 1.
* Bad, because a manifest that contradicts its files is read as if nothing were wrong, and a warning in
  CI goes unread.

### Fork 4 — Pointers without a field

**(a) Both pointers gain an optional field. ✅ Chosen.**
* Good, because it is additive within `2.x`, and a manifest written before this ADR stays valid.
* Good, because NFR-7 AC-1 is met for both.
* Bad, because the field is optional in the schema though always written, and a reader must handle a
  pointer without it.

**(b) Move them under `artefacts`.**
* Good, because every indexed file then has one pointer shape.
* Good, because the version field comes with it.
* Bad, because it restructures the manifest against ADR-025 Fork 2's grouping, and breaks `2.x` readers.

**(c) Exempt them.**
* Good, because nothing changes.
* Good, because their files carry the version.
* Bad, because NFR-7 AC-1 is not met for them.

### Fork 5 — Bumps per release

**(a) One per schema per release, major or minor. ✅ Chosen.**
* Good, because a consumer migrates at most once per schema per release.
* Good, because the number says how many incompatible lines exist, not how many changes made them.
* Good, because additive changes from clusters that ship together merge into one minor, so no version
  exists that no release wrote.
* Bad, because one major can carry several unrelated breaking changes, which the changelog must list.

**(b) One per change.**
* Good, because each change is visible in the number.
* Good, because a change is traced to its bump.
* Bad, because a consumer sees several majors in one release, with no version in between ever shipped.
* Bad, because several additive changes give several minors in one release, each a version a consumer
  could pin that no release wrote.

## More Information

### Relationships

* **ADR-006** (knowledge graph schema) — on acceptance, Fork 6 (d) and the statements listed in its
  constraint are superseded by Forks 1 and 2.
* **ADR-025** (manifest schema) — on acceptance, Fork 4's version-authority statements are superseded;
  two pointers gain a field (Fork 4).
* **ADR-017** (evaluation framework) — the scorecards carry their version in the file; this rule covers
  them by name. Its skip for a changed compile-check record, and its graph `schema_validity` check, are
  as Fork 3 and the constraint above state.
* **ADR-028** (what a command may overwrite, delete or refuse) — its Fork 3 refuses earlier-layout run
  directories; the read path runs in its step 1. For a command that publishes, its Fork 5 recovery runs
  before any version is read; a command that publishes nothing reports a journal it cannot recover and
  proceeds, which is the window Fork 3's message covers. It owns the format of claims, the lock and the
  journal, and is conformed (above).
* **ADR-029** (output layout and ownership) and **ADR-033** (extraction environment and parser failures)
  — their records follow this rule.
* **ADR-031** (command outcomes and consent) — conformed: a version the tool does not read takes status
  3, a disagreement status 1.
* **ADR-032** (evaluation semantics) — conformed (above); its skips for a changed file take precedence
  over Fork 3.
* **ADR-022** (run manifest and structured logging) — its strict-write, lenient-read rule and freshness
  gate are the pattern Forks 1 and 5 extend to every schema.
* **ADR-026** (release version management) — schema versions are separate from the application version
  (NFR-7 AC-2); every release applies Fork 5.
* **ADR-027** (cost-safety floor) — estimates the LLM calls a re-created run re-pays.
* **ADR-007** (golden-graph pattern) — one `change` refresh.

### Requirements touched

* **NFR-7 AC-1** — every artefact declares its version in the file and in the manifest (Forks 1, 4).
* **NFR-7 AC-3** — within a major, evolution is additive; a breaking change starts a new major line
  (Fork 5, which also bounds the bumps to one per schema per release).
* **FR-2, FR-34 AC-4** — the graph is usable on its own (Fork 1).
* **FR-7b AC-1, AC-3** — every emitted graph and enrichment file validates against its published schema,
  which pins its major; earlier majors' schemas stay committed (Fork 1). Writes validate strictly, reads
  and the schema-validity checks against the file's major (Fork 5).
* **FR-45 AC-2** — a refusal changes nothing: the read path runs in ADR-028's step 1.

### References

* Requirements — `docs/requirements.md` (NFR-6, NFR-7, FR-2, FR-7b, FR-17, FR-34, FR-45).
* Manifest version log — `docs/manifest-versions.md`.
* SARIF 2.1.0 — `version` property.
* CycloneDX — `specVersion`.
* SPDX — `spdxVersion`.
* OpenAPI — `openapi` field.
* npm — `package-lock.json` `lockfileVersion`.
* OCI image manifest — `schemaVersion`.

### Deferred

* **Reading more than one major of a schema.** In v1 a tool reads one major per schema (Fork 2), so each
  new major forces a re-creation. Trigger: the `1.0.0` stability gate (ADR-026 Fork 3), when a
  compatibility promise is made.

### Open questions

* None.

## Revision history

* **2026-11-19** — code citations replaced by descriptions of the behaviour; the commit anchor replaced by
  the release the Context describes; repetition cut. No fork, option, decision or rule changed.
