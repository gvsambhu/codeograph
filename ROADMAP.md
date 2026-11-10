# Roadmap

What Codeograph covers today, what is planned, and how its versions and labels relate. Older documents,
branch names and commit messages use some labels that are no longer current; each is explained under
[Labels in the history](#labels-in-the-history), so an old reference never has to be guessed at.

## Versions

Codeograph follows [Semantic Versioning](https://semver.org/) ([ADR-026](docs/adr/ADR-026-release-version-management.md)).

- **The current version** is in `pyproject.toml`, and `codeograph --version` prints it. While it is below
  `1.0.0`, the command line and the output formats may change between any two releases.
- **`1.0.0` is reserved for the stability gate** — the point at which the command line and the output
  schemas are frozen, after which changes stay backward compatible.
- **No release has been tagged yet; the first will be.** Until then, *shipped* in this repository means
  *merged to `main`*.

Each output format has its own schema version line, independent of the package version (NFR-7); the
manifest's own history is in [`docs/manifest-versions.md`](docs/manifest-versions.md). A consumer pins the
format, not the tool.

## Scopes

Work is planned in scopes. **A scope is one outcome, and it is finished when every requirement it owns has
shipped and been verified** against the code and the repository's settings. Its state is read from the
[requirements' status table](docs/requirements.md#7-status). A scope is **not a version number**: it can
take several releases, and *Shipped in* names the first tagged release that contains the finished scope.

| Scope | Outcome | Requirements | State | Shipped in |
|---|---|---|---|---|
| **SC-001: Deterministic graph** | Point it at a Java/Spring project — a directory, a git URL or a `.zip` — and get a knowledge graph whose structural facts come out the same on every run, with complexity metrics, a manifest and a run log, independent of any render target | FR-1, FR-2, FR-10, FR-12, FR-20, FR-29 | In progress | — |
| **SC-002: Complete, honest extraction** | The graph records everything in the source and nothing an LLM returned, byte for byte the same on every run; unusable input fails with its cause named; every artefact matches its published, versioned schema and the hash its manifest records | FR-7b, FR-24, FR-30, FR-31, FR-32, FR-33, FR-34, FR-40, NFR-6, NFR-7 | In progress | — |
| **SC-003: LLM enrichment** | An LLM adds semantic facts *about* the graph — kept apart from it and joined by node identity — through the provider the user chooses; input repeated across calls is not paid for in full, and an enrichment failure costs quality, not the run | FR-8, FR-11, FR-35, NFR-2 | In progress | — |
| **SC-004: Accountable LLM use** | Every LLM call is recorded on the user's machine, made with a versioned prompt and within a bounded spend; a response is reused only for an identical request, from a cache the user can inspect and purge; credentials stay secret and settings resolve in a documented order; data goes only where the user directs it, and LLM output never decides what the tool writes, runs or contacts | FR-15, FR-16, FR-17, FR-37, FR-38, FR-39 (except AC-5 to AC-7, in SC-012), FR-46, NFR-8 | In progress | — |
| **SC-005: TypeScript rendering** | The graph renders to idiomatic TypeScript/NestJS, selected at invocation behind a boundary a new target does not cross, capped and selected predictably, with no source feature silently dropped | FR-3, FR-5, FR-13, FR-14, FR-36, NFR-5 (except AC-2, in SC-009) | In progress | — |
| **SC-006: Evaluation** | The graph and the rendered source are scored reproducibly, each LLM-derived score records the model that produced it, and a complete example run is committed per target | FR-7, FR-7a, FR-9, FR-18, NFR-3 — FR-7a's semantic-accuracy check completes with SC-010 | In progress | — |
| **SC-007: Engineering assurance** | Every change is tested, regression-checked against committed goldens and scanned for secrets before it merges, and the full history is scanned on a schedule | FR-7c (except AC-2, in SC-010), FR-19 (except AC-4, in SC-013), FR-21, NFR-4 | In progress | — |
| **SC-008: Safe re-runs** | Re-running never loses work: earlier output is preserved, content the tool did not produce is never damaged, concurrent invocations cannot corrupt each other, every invocation's outcome is recorded and distinguishable, and risky operations ask first | FR-27, FR-42, FR-43, FR-44, FR-45 | In progress — design: [ADR-028](docs/adr/ADR-028-overwrite-delete-and-refuse.md) to [ADR-031](docs/adr/ADR-031-command-outcomes-and-consent.md), proposed | — |
| **SC-009: Second render target** | The graph renders into idiomatic Go, and how to add a target is documented step by step | FR-4, NFR-5 AC-2, and Go's share of the obligations every target carries — FR-7, FR-9, FR-36 AC-4, NFR-4 AC-3 | Planned — design: ADR-011 and ADR-012, reserved | — |
| **SC-010: Measured quality** | Graph correctness is measured against a human-validated expectation, LLM-judge scores are calibrated against known-good and known-bad output, and a real-world project has a committed golden | FR-25, FR-41, FR-7c AC-2 | Planned | — |
| **SC-011: Determinism contract** | Re-rendering a fixed input gives identical bytes, and every field of every artefact schema is documented as deterministic or not | FR-23, FR-28 | Planned | — |
| **SC-012: Spend in money** | A dry run prices an invocation without paid calls, a ceiling in money stops it on projected or accumulated spend, and its token use and cost are reported at the end | FR-39 AC-5, AC-6, AC-7 | Planned | — |
| **SC-013: Untrusted input** | Instructions planted in the analysed source reach the LLM as data, with the remaining risk documented, and every malformed-input failure class has a test | FR-26, FR-19 AC-4 | Planned | — |

### How a scope's state is read

| State | When |
|---|---|
| **Planned** | None of the requirements it owns is built yet — every one is `planned` in the status table |
| **In progress** | Some are `partial` or `shipped`, but not all are shipped and verified. The status table lists where each falls short; the README's [Known gaps](README.md#known-gaps) lists those a user would notice |
| **Done** | Every requirement it owns is shipped and verified against the code and the repository's settings |

A criterion a scope owns counts as built when the status table's note says it holds, so a scope that owns
some of a requirement's criteria is read from the note, not the requirement's status. A scope's design is
shown as a note beside its state, not as a state of its own.

### What a scope owns

- **A requirement belongs to one scope.** Where some of its acceptance criteria belong to another, both
  rows say so, and each scope counts only the criteria it owns.
- **Where a requirement's statement, rather than one of its criteria, depends on another scope**, the row
  names that scope — as SC-006 does for FR-7a.
- **Obligations that apply to every render target** are met for a new target inside the scope that adds
  it, so a finished scope does not reopen when a target is added.

**A scope ID is permanent** — never renumbered or reused. When a scope is split, the original keeps its ID
with a narrower outcome and the new part takes the next free ID. The numbers do not show the order of work.

### Retired scopes

None.

### Proposed directions

Directions the project intends to take, with no requirements written yet. Each gets a scope ID when its
requirements are written.

- **Source neutrality** — analysing source languages other than Java, which the
  [requirements](docs/requirements.md#2-scope) currently put out of scope. It would need the knowledge graph
  to stop assuming Java and Spring.
- **Knowledge wiki** — human-readable documentation of an analysed codebase, generated from the same
  knowledge graph and LLM annotations the renderers use.

### Considered, not scheduled

Smaller items that may be taken up; none is planned.

- A dependency lockfile.
- A changelog.
- Progress reporting during a long run.
- Ollama and Amazon Bedrock as LLM providers.
- A curated mapping of models to pipeline stages.
- Batched LLM calls through the provider's batch API.
- CI on Windows and macOS as well as Linux.
- Log rotation and coloured console output.

## Labels in the history

These labels come from how the work was organised. New documents describe the work instead of citing
them; they are listed so that older references stay readable.

| Label | Where you will see it | Meaning |
|---|---|---|
| `v1`, `v1.1` | ADRs, older documents | Former names of the scopes, not version numbers. **v1** is SC-001 to SC-008. **v1.1** means *deferred from the first scope*: SC-009 to SC-013, the items under *Considered, not scheduled*, and smaller deferrals recorded in individual ADRs |
| `DC1` … `DC6` | Commit messages, older documents | The six development chunks that built the core pipeline: **DC1** the deterministic graph pipeline; **DC2** LLM enrichment, the response cache and telemetry; **DC3** the TypeScript/NestJS renderer; **DC4** the evaluation framework; **DC5** the flat run manifest, structured logging and secret scanning; **DC6** the cost-safety floor and multi-provider LLM support |
| `M1`, `M2`, … in a commit message | Commit messages | A numbered step within one development chunk. The same number in two chunks names two different steps |
| `DC3-01`, `DC4-D`, `DC1R-10`, … | Commit messages | A numbered or lettered item raised while reviewing a development chunk, fixed by that commit; `R` marks an item from the review that checks the code against its ADRs |
| `fixup-01`, … | Commit messages and branch names | A round of corrections to a chunk after it merged |
| `M1`, `M2` inside ADR-002 and ADR-005 | Those ADRs | Option labels within a decision — unrelated to the commit-message steps |
| *Fork n* | ADRs | One decision point inside an ADR, with its options |
| `D-NNN-n` (e.g. `D-009-1`) | ADRs | A design-review decision recorded inside ADR-NNN |
| `F-NNN-n` (e.g. `F-005-7`) | ADRs | A design-review finding recorded inside ADR-NNN that changed its text but no decision |
| `FR-n`, `NFR-n`, `AC-n` | Everywhere | A requirement and its acceptance criteria ([`docs/requirements.md`](docs/requirements.md)). Numbers are permanent identities, not positions |
| `design/r<n>-…`, `design/dc<n>-…` | Branch names | Design round *n* — ADR drafting; earlier, a development chunk's design work |
| `dev/dc<n>-…`, `dev/feature-<n>`, `dev/docs-<n>-…`, `dev/fix-<n>-…`, `bugs/…` | Branch names | Development chunk *n*; documentation change *n*; a standalone fix |

## How this file changes

- **A requirement is added** — it is assigned to a scope in the same change. A *Done* scope it joins
  returns to *In progress*.
- **A requirement is retired** — it leaves its scope's row in the same change that retires it.
- **A requirement moves to another scope** — its old and new rows change together.
- **A *Done* scope regresses, or a re-verification finds a shipped requirement is not** — the scope returns
  to *In progress*; its *Shipped in* keeps the release that first contained it, with a note.
- **Scopes are merged** — the absorbed ID moves to *Retired scopes*, with where its work went.
- **A release is tagged** — every scope that is *Done* and has no *Shipped in* records it.
- **A direction's requirements are written** — it becomes a scope with the next free ID, or its
  requirements join an existing scope.
- **The status table and this file disagree** — the status table wins, and this file is corrected in the
  same change as the status row.
- **A label is retired** — it moves to *Labels in the history* with its meaning; it is never just deleted,
  so older references keep resolving.
