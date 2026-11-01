---
status: proposed
date: 2026-10-31
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-029 — Output Layout and Ownership

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `bd6a837` (2026-10-31). File and
line references are to that commit.

**ADR-022 Fork 5** locked a per-run directory layout by formalising the pattern shipped at the time: a
single `<out>` root holding the manifest, the logs, the graph, the annotations, the telemetry, the
rendered target tree and the evaluations. It stated its own assumption plainly — *"`<out>` **is** the
per-run directory"*, with multi-run history left to *"user discipline — users wanting persistent
multi-run history use distinct `--out` paths per run"*.

**The code diverged from that layout in three places, none recorded as a decision:**

| # | ADR-022 Fork 5 specified | Shipped | Evidence |
|---|---|---|---|
| 1 | `<out>/telemetry/` | `~/.codeograph/cache/telemetry/` | `telemetry/session_manager.py:22` derives it as `cache_dir / "telemetry"` |
| 2 | rendered source under `<out>/` | its own mandatory `--out` root | `cli/render.py:59,70,172` |
| 3 | rendered source under `<out>/<target>/` | the root of render's `--out`, no target segment | `renderers/typescript_nestjs/scaffold_emitter.py:65,71` (root-relative keys such as `package.json`, `src/main.ts`) |

**What the divergence breaks:**

- **The documented multi-pass workflow cannot be completed in one directory.**
  `docs/running-codeograph.md` recommends `run --ast-only` followed by a full run into the same
  directory. The second command is refused as non-empty; `--force` "resolves" it by clearing the
  directory, including the graph the first command produced.
- **The compile-check record lands outside the run directory.** Render adds
  `evals/compile-checks.<target>.json` to the rendered project's file map
  (`cli/render_pipeline.py:152-154`), so it is written under render's `--out` while its manifest pointer
  is stored in the run's manifest — two roots, nothing reconciling them.
- **`eval` finds render targets by exclusion** — every directory except `evals` and `.codeograph`
  (`cli/eval.py:81`, duplicated at `evals/corpus_evaluator.py:50`). `telemetry` is not on that list, so
  under ADR-022 Fork 5 as written, `eval` would have scored a telemetry directory as a target.
- **The compile check already assumes ADR-022's layout** — it resolves the tree at `<out>/<target>/`
  (`evals/checks/code/compile.py:114`), which the split layout never produces.
- **Corpus synthesis writes into the deterministic graph.** Pass 2 adds `projectOverview` to `graph.json`
  after the graph is written and hashed (`passes/pass2/corpus_synthesizer.py:89`), so on any LLM-enabled
  run the graph is no longer a function of the corpus alone, and the manifest's hash describes a file
  that is no longer on disk.

**And the requirements ask for more than a single root can give.** The rendered source is placed
where the user chooses, or at a documented default (**FR-3 AC-3**); every artefact other than the
rendered source stays inside the output directory (**FR-27 AC-1**); and an output directory is reused by
every later command against the same run (glossary, *Output directory*). Those are three different
answers to "where does this go", and one `<out>` cannot carry all three.

**This ADR decides where every output lives and which command writes it.** It is one of four coupled
decisions about the output layout, reviewed and accepted together:

| ADR | Decides |
|---|---|
| **ADR-029** (this) | Where each output lives, and which command writes it |
| ADR-028 | What a command may overwrite, delete or refuse — the safety rules applied to this layout |
| ADR-030 | How each invocation is identified, and how the history of an output directory is kept |
| ADR-031 | How every command reports its outcome and asks for consent |

What the manifest indexes, and how a stale artefact is detected, are amendments to **ADR-025**.

**It partially supersedes ADR-022: Fork 5 only.** ADR-022's logging forks remain in force, as do its
manifest forks already superseded by ADR-025.

## Decision Drivers

* **Visibility of every run** — every kind of invocation, and everything it produced, is found in one
  directory, under one rule.
* **Least surprise** — re-running into the same directory works; the deliverable sits beside the user's
  work, not in a hidden folder; the defaults fit the common cases — analyse once, iterate, convert and take
  the project away, evaluate, compare two runs, run in CI, keep editing the generated project.
* **Every default can be changed** — no location is hard-wired (FR-3 AC-3, FR-38 AC-1).
* **Shared state lives outside any run** — the response cache and telemetry in one known place.
* **A rendered project contains nothing of the tool's** — it is a deliverable the user takes away and
  edits.
* **Renderer ergonomics** — adding a render target touches only its own package (NFR-5 AC-1).
* **Determinism boundary clarity** — the graph holds no LLM output, so it stays a function of the corpus
  alone (FR-34).
* **One placement rule** — where an output lives follows from a stated rule, not from precedent, so a new
  output has a home without a new decision.

## Considered Options

### Fork 1 — How many output locations, and which is fixed

* (a) One root for everything — the rendered project always lives inside the run directory.
* (b) Two independent roots, both chosen by the user — the shipped split.
* **(c) Two outputs: the run directory holds everything except the rendered source; each target's
  rendered source goes where the user chooses, defaulting to a folder inside the run directory. ✅**
* (d) The user's chosen folder is the rendered project, and the run's metadata goes beside it.

### Fork 2 — How the run directory is chosen

* (a) Always required — no default (the shipped behaviour).
* (b) A hidden folder under the user's home, e.g. `~/.codeograph/runs/<name>-<id>/`.
* (c) A visible folder under the user's home, e.g. `~/codeograph-runs/<name>-<id>/`.
* **(d) A folder under the current directory, `./codeograph-out/<name>-<id>/`, with the parent folder a
  setting (`runs_dir`) so a fixed location is one setting away. ✅**

### Fork 3 — Naming a target's source folder, and who composes the path

* (a) The bare target name at the root — `ts/`, `go/`.
* (b) A container — `target/ts/`, `target/go/`.
* **(c) A suffixed name — `ts-source/`, `go-source/` — as the default only; the command line composes
  the path, and a renderer never learns where it is written. ✅**

### Fork 4 — Namespaces inside the run directory

* (a) Status quo — the run's artefacts bare at the root, `evals/` namespaced.
* **(b) Every kind of output namespaced; the root holds only the index files. ✅**
* (c) Full symmetry, the manifest included — `run/manifest.json`.

### Fork 5 — What lives outside a run

* **(a) Three classes by one rule: run output inside the run directory; shared state (response cache,
  telemetry) under a per-user home; temporary files (acquired source) outside both. ✅**
* (b) Everything inside the run directory, cache and telemetry included.
* (c) Both — a copy per run and an aggregate under the home.
* (d) Two classes only — the rule covers outputs, and temporary files are not classified.

### Fork 6 — Where render's own records live

* **(a) The run's `evals/` directory, beside the scorecards. ✅**
* (b) Inside the rendered project — `ts-source/evals/`.
* (c) A dedicated `render/` namespace in the run directory.

### Fork 7 — Where corpus synthesis lives

* (a) A corpus-level section inside the annotations file.
* **(b) Its own artefact, `analysis/corpus-synthesis.json`. ✅**
* (c) Status quo — a `projectOverview` field in the graph. *Not available: FR-34 AC-1.*

## Decision Outcome

### Fork 1 — Two outputs: (c)

```
<run directory>/                 ← chosen per Fork 2; every command against the run uses it
  …                              ← metadata, artefacts, records (Fork 4)
  ts-source/                     ← default home of the TypeScript project (Fork 3)
<anywhere the user chooses>/     ← render … --source-out <dir> places the project there instead
```

**The run directory** holds the manifest, the analysis artefacts, the evaluations, the logs, the
invocation history and each target's file list — everything except a rendered project. It is the
**output directory** of the requirements glossary, and every command against the run reads and writes
it.

**Each target's rendered source** defaults to `<run directory>/<target>-source/`. `render --source-out
<dir>` places it anywhere else; the path is then used **as given** — no suffix is appended.

**Inside or outside is decided on resolved paths**, never on the text typed: made absolute, `.` and `..`
collapsed, symbolic links and junctions followed, compared case-insensitively on Windows. A different
drive is outside; one network location reached through two names is treated as outside (safe, less
portable). How each kind is recorded in the manifest is ADR-025's.

**Locations that are refused:**

| Location | Refused for | Why |
|---|---|---|
| The current working directory, or an ancestor of it | the run directory | FR-27 AC-2 |
| A folder with content that is not a run directory — no manifest, no history | the run directory | It holds someone else's files (FR-27 AC-5; the plan's output-path intent). *Empty means empty* — a folder holding only `.git` is not empty |
| The run directory itself | a rendered project | Project files would sit beside the manifest — the original defect |
| An ancestor of the run directory | a rendered project | The project would contain the run's metadata |
| Anything inside `analysis/`, `evals/`, `logs/`, `.locks/`, or the archive location (ADR-028) | a rendered project | Those namespaces belong to other writers (Fork 4) |

**A re-render without `--source-out` reuses the recorded location.** Moving a project is always an
explicit act. A relative `--source-out` resolves against the current directory, like every path argument.

**Targets coexist.** Rendering a second target leaves every other target's project untouched — the
source folders are disjoint, and every per-target record is named for its target. **One target per
`render` invocation** is assumed throughout.

**`eval` finds the rendered targets from the manifest only.** The folder name is a default, not an
identifier, so the exclusion list in `cli/eval.py` and `evals/corpus_evaluator.py` is retired.

### Fork 2 — `./codeograph-out/<name>-<id>/`, configurable: (d)

**The run directory is the last positional argument of every command** that works on a run:

```
codeograph run     <source> [<run directory>]
codeograph render  <run directory> --target ts [--source-out <dir>]
codeograph eval run <run directory>
```

`history <run directory>` and `purge <run directory>` follow the same rule (ADR-030, ADR-028), and
`eval report` takes one or more run directories and writes its report to standard output, or to
`--output <file>` — never inside a run directory it reads. **The previous flags are removed outright,
with no alias** — `run --out`, `render --from` and `render --out`.

**Resolution when `run` is given no directory:**
1. Given explicitly → used as given (a relative path resolves against the current directory).
2. Otherwise → `<runs_dir>/<name>-<id>/`, where `runs_dir` is a setting (`CODEOGRAPH_RUNS_DIR`) whose
   default value is `./codeograph-out`. A relative value means *where the command runs*; an absolute value
   means one fixed place. `<name>` is the source's name and `<id>` a short hash of its identity, so two
   projects that share a name never share a directory, and the same source re-runs into the same directory:

   | Source | `<name>` | Identity hashed for `<id>` |
   |---|---|---|
   | Local folder | the folder's name | its resolved absolute path |
   | Git URL | the repository's name | the URL, with any credentials removed |
   | Zip archive | the file name without its extension | its resolved absolute path |

   `<id>` is the first 8 hex characters of the identity's SHA-256. **`<name>` is made safe for every file
   system:** characters outside `A–Z a–z 0–9 . _ -` become `-`, repeats collapse, it is cut to 40
   characters, a Windows reserved name (`CON`, `NUL`, …) gains a `_` prefix, and an empty result becomes
   `source`. **Identity follows the location:** moving or renaming a project folder starts a new run
   directory, and its history does not follow; a git URL's identity ignores the branch, so to compare two
   branches, name a run directory for each.

The chosen path is always printed. **Run output is the deliverable, so it lives in view**, beside the
user's work — not in a hidden folder, which is where tool state belongs (Fork 5).

**Two protections make a default inside the analysed project safe:**
- **Source discovery skips any run directory**, recognised by its manifest or history file, not by its
  name — so a custom-named run directory inside a project is skipped too. **The skip is reported** with the
  other exclusions (FR-30 AC-4).
- **A self-ignoring `.gitignore`** (`*`) is written inside the run directory **when the tool chose the
  location** — git then ignores it without any edit to the user's own `.gitignore`. A directory the user
  named gets none, so a run committed on purpose (FR-9's examples) stays committable. **The tool never
  edits the user's `.gitignore`.**

**Known limits** (documented, not engineered around): a Docker build context with `COPY .` picks the
folder up; editors may index it; version-control systems other than git are not covered.

**Path length on Windows.** The default nesting (`codeograph-out/<name>-<id>/ts-source/…`) and the
archive's (`archive/<time>-<invocation id>/…`) lengthen every path. Where a path would exceed Windows'
260-character limit and long-path support is not enabled, the command fails before writing, naming
`runs_dir` and `--source-out` as the remedy — never a partial write.

### Fork 3 — `<target>-source/` as the default, composed by the CLI: (c)

```
<run directory>/ts-source/     <run directory>/go-source/
```

**The suffix is a default, not an identifier** — `eval` identifies targets from the manifest (Fork 1).
It keeps every directory named for what it contains: `analysis/`, `evals/`, `logs/`, `ts-source/`. A
`target/` container would name a role, and *target* already means the build-output root to the Maven and
Cargo audience.

**The command line composes the path.** A renderer returns its files as paths relative to the project
root (ADR-008's contract) and never learns where they are written; the command line joins them to
`<run directory>/<target>-source/` or to `--source-out`. A future renderer cannot forget a rule it never
has to follow.

### Fork 4 — Every kind of output namespaced: (b)

```
<run directory>/
├── manifest.json                 ← the index (ADR-025)
├── runs.jsonl                    ← invocation history (ADR-030)
├── ts-source.files.json          ← each rendered target's file list (ADR-025 amendment)
├── .gitignore                    ← only when the tool chose the location (Fork 2)
├── analysis/
│   ├── graph.json                ← Pass 0
│   ├── llm-annotations.json      ← Pass 1
│   └── corpus-synthesis.json     ← Pass 2 (Fork 7)
├── evals/
│   ├── graph-scorecard.json
│   ├── ts-scorecard.json
│   ├── ts-scorecard.compile.<name>.log
│   ├── compile-checks.ts.json    ← render (Fork 6)
│   └── render-audit.ts.json      ← render (Fork 6)
├── logs/                         ← one file per invocation (ADR-030)
├── archive/                      ← superseded output (ADR-028)
├── .locks/                       ← claims, the brief lock and the recovery journal (ADR-028)
└── ts-source/                    ← default project location (Fork 3)
```

**The root holds only index files** — the manifest, the history, each target's file list, and the
ignore file — plus `.locks/`, which is transient: empty whenever no invocation is running. A file list is part of the manifest's integrity record, not an output of its own, so it
sits with the manifest rather than in a namespace.

**`manifest.json` stays at the root** because every consumer starts there (ADR-017 resolves it at the
root, and `eval run <run directory>` reads it first); ADR-022 rejected moving it for the same reason. This
is the shape of the comparable tools: Maven keeps its output under `target/`
([standard directory layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)),
Cargo under `target/` with one subdirectory per profile
([build cache](https://doc.rust-lang.org/cargo/reference/build-cache.html)), dbt under its target path
([`target-path`](https://docs.getdbt.com/reference/project-configs/target-path)). In each, phases add to
one root, and removing output is a separate command, never a side effect of building.

**`analysis/`, not `graph/`.** It holds the graph **and** the LLM's annotations, and those are
deliberately separate artefacts (FR-34). `graph/` would claim the annotations are part of the graph —
the conflation the architecture exists to prevent. `analysis/` covers both and collides with no defined
term.

### Fork 5 — Three classes by one rule: (a)

```
~/.codeograph/          ← home_dir: per user
├── cache/cache.db      ← the response cache
└── telemetry/          ← per-call telemetry
```

**The rule every output follows, now and later:**

> **Does anything read it after this invocation?**
> **No → temporary**: outside both, removed when the invocation ends (FR-29 AC-5).
> **Yes, across runs → shared**: under `home_dir`.
> **Yes, within one run → run output**: inside the run directory.

It places everything with no special case: an acquired git clone or unzipped archive is temporary; the
response cache is shared (its whole purpose is reuse across runs — its key deliberately carries no run
identity, so a per-run cache would never hit); telemetry is shared (the cache report aggregates it across
runs); everything else is run output.

**Telemetry and the cache become siblings.** Telemetry's location was never chosen — it was derived as
`cache_dir / "telemetry"`. It is a diagnostic record, not part of the cache.

**Settings.** `home_dir` (default `~/.codeograph`; `CODEOGRAPH_HOME`, with `CODEOGRAPH_HOME_DIR`
accepted under ADR-001's naming rule). `cache_dir` and `telemetry_dir` default to `home_dir / "cache"`
and `home_dir / "telemetry"`, each still separately settable; an existing `CODEOGRAPH_CACHE_DIR` keeps
working. *Home* rather than *global*: the folder is per user account, which `*_HOME` names correctly
(`JAVA_HOME`, `CARGO_HOME`).

**An unusable `home_dir` or `runs_dir`** — unwritable, or a file where a folder is expected — **fails at
startup** with a message naming the setting (FR-38 AC-2), never mid-run.

### Fork 6 — Render's records in the run's `evals/`: (a)

Render writes two records of its own, both under `<run directory>/evals/`:

| File | Holds |
|---|---|
| `compile-checks.<target>.json` | The compile commands evaluation runs against the rendered project |
| `render-audit.<target>.json` | What render selected, skipped and refused, and by which rule (FR-14 AC-3; FR-36). **Its contents are decided with ADR-017 and ADR-010**; this ADR fixes only its location |

**The rendered project contains nothing of the tool's.** Inside the project (b), the records would be
committed with the user's application — the project's own `.gitignore` is a stock Node ignore. A
`render/` namespace (c) would split the evaluation inputs from the evaluation outputs, and `eval` reads
both.

**The boundary already exists in code.** A renderer returns only target-stack files; the pipeline adds
the compile-check record at one place (`cli/render_pipeline.py:152-154`). This decision moves that one
write to the run directory.

### Fork 7 — Corpus synthesis in its own artefact: (b)

```
<run directory>/analysis/corpus-synthesis.json      ← Pass 2
```

**Pass 2's output leaves the graph.** It is LLM-derived, so FR-34 AC-1 forbids it there.

**Its own file, because each pass then owns exactly one:** Pass 0 the graph, Pass 1 the annotations,
Pass 2 the synthesis — no pass rewrites another's output. A later pass rewriting an earlier pass's file
is precisely what broke the graph's integrity; a section inside the annotations file (a) would move that
pattern rather than remove it.

**A failed synthesis becomes representable** as one missing artefact beside intact annotations (FR-35
AC-1); how the manifest records it is ADR-025's.

**Removing `projectOverview` from the graph is a breaking change** to a published schema (NFR-7 AC-4).
Its version consequence is stated with this cluster's other version consequences.

### Ownership

**Ownership is per file, not per directory.** `evals/` has two writers, so the assumption that a
command owns every directory it writes to would let one delete the other's records.

| Path | Written by |
|---|---|
| `manifest.json` | `run` creates it; `render` and `eval` each write only their own sections (ADR-025) |
| `runs.jsonl`, `logs/<invocation>.jsonl` | every invocation, its own entries and its own log (ADR-030) |
| `analysis/graph.json` · `llm-annotations.json` · `corpus-synthesis.json` | `run` — Pass 0, Pass 1, Pass 2 respectively |
| `<target>-source/**` (or the `--source-out` location) · `<target>-source.files.json` · `evals/compile-checks.<target>.json` · `evals/render-audit.<target>.json` | `render` |
| `evals/*-scorecard.json` · `evals/*-scorecard.compile.<name>.log` | `eval` |
| `<run directory>/archive/` (everything under it) | the invocation that supersedes the output (ADR-028) |
| `.locks/**` | each running invocation, its own claims; the brief lock while held (ADR-028) |
| `.gitignore` | `run`, only when it chose the location |
| `eval report`'s report | `eval report` — standard output, or `--output <file>`; never inside a run directory it reads |

ADR-028 applies its overwrite and deletion rules to this table.

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-025
The manifest indexes the synthesis artefact (Fork 7), each rendered target's file list and project
location — relative when inside the run directory, absolute when outside, by Fork 1's resolution — and
lets `render` and `eval` each write only their own sections.

#### Constraint flagged for ADR-017
`eval` identifies targets from the manifest and the exclusion list is retired (Fork 1); the compile
check resolves the project from its recorded location, not `<run directory>/<target>/`; render's
records are read from `evals/` (Fork 6).

#### Constraint flagged for ADR-010 and ADR-017
The render audit leaves the manifest for `evals/render-audit.<target>.json` (Fork 6); its contents —
what was selected, skipped and refused, and by which rule — are decided by the two together.

#### Constraint flagged for ADR-015
Telemetry moves to `<home_dir>/telemetry/`, a sibling of the cache (Fork 5).

#### Constraint flagged for ADR-006
`projectOverview` is removed from the graph schema (Fork 7).

#### Constraint flagged for ADR-030
`runs.jsonl` and the per-invocation log files under `logs/` are its to define (Fork 4).

#### Constraint flagged for ADR-031
Every refusal named here — a refused location, a misconfigured `home_dir` or `runs_dir` — carries the
status ADR-031 assigns.

#### Constraint flagged for ADR-026
The cluster's version consequences, applied when the code ships (ADR-026: the bump is decided at
release): **the tool goes to `0.6.0`** — in `0.x` a MINOR carries the command-line break, and `1.0.0`
stays the stability gate; **the graph schema takes its next MAJOR** (`projectOverview` removed, ADR-006);
**the manifest schema becomes `2.2.0`** (additive, ADR-025); **the scorecard schema takes its next MINOR**
(input fingerprints added, ADR-017); **the new formats start at `1.0.0`** — the file list, corpus
synthesis, the history and the render audit.

## Consequences

**Positive.**
1. The documented multi-pass workflow completes in one directory.
2. A rendered project can be placed anywhere without moving the metadata; by default the two stay
   together.
3. The compile-check record and its pointer share one root, and `eval` finds targets from the manifest
   instead of by elimination.
4. The graph is byte-reproducible on LLM-enabled runs again (FR-34 AC-3).
5. Shared state has one documented home, and acquired source always has a cleanup rule.
6. Every location follows a stated rule, so the next output needs no new layout decision.

**Negative.**
1. Every artefact path changes; the committed example runs are regenerated in the new layout, and the
   goldens and docs updated.
2. The command-line shape changes — the run directory becomes positional, and `--out` and `--from` are
   removed with no alias — so existing scripts break.
3. The graph schema loses `projectOverview`, a breaking change to a published schema.
4. A run directory alone no longer holds everything needed to diagnose a run; telemetry under `home_dir`
   is joined to it by invocation identifier.
5. A default run directory inside the analysed project relies on two protections that cover neither Docker
   build contexts nor editor indexing, nor version-control systems other than git.
6. A relocated project is recorded by absolute path, so a copied run directory can lose the link to it —
   the file list still verifies the project wherever it is.

## Confirmation

1. `codeograph run <corpus> --ast-only` followed by `codeograph run <corpus>` into the same run directory
   succeeds without any overriding option (integration test — the documented multi-pass sequence).
2. `codeograph run <corpus>` with no directory writes to `./codeograph-out/<name>-<id>/`; with
   `CODEOGRAPH_RUNS_DIR` set to an absolute path, it writes under that path; two corpora with the same
   name get different directories (integration test).
3. `codeograph render <run> --target ts` writes `<run>/ts-source/package.json`; with
   `--source-out <dir>` it writes `<dir>/package.json` and nothing under `<run>/ts-source/`; a later render
   without `--source-out` writes to `<dir>` again (integration test).
4. `--source-out` pointing at the run directory, an ancestor of it, or any path inside `analysis/`,
   `evals/`, `logs/`, `.locks/` or the archive location is refused before anything is written; a run directory that is the
   current directory or an ancestor of it is refused (unit tests on path resolution, including a symbolic
   link and, on Windows, a case variant).
5. A renderer's returned file keys contain no `<target>-source` prefix (unit test on `renderer.render()`).
6. Rendering `ts` then `go` into one run leaves both projects present; `eval` scores both, found from
   the manifest, and the exclusion tuple `("evals", ".codeograph")` no longer exists in `cli/eval.py` or
   `evals/corpus_evaluator.py` (integration test + grep).
7. The rendered project contains no file the renderer did not return — in particular no `evals/`
   directory; the compile-check and render-audit records are under `<run>/evals/` (integration test).
8. Source discovery over a project containing a run directory — default-named or custom-named — leaves
   every file under it out of the corpus and reports the skip (integration test).
9. The tool writes `.gitignore` inside a run directory it chose, and none inside one the user named; no
   test run modifies a `.gitignore` outside the run directory (integration test).
10. With no `CODEOGRAPH_HOME` set, the cache is `~/.codeograph/cache/cache.db` and telemetry is under
    `~/.codeograph/telemetry/` — siblings; `CODEOGRAPH_HOME` relocates both; `CODEOGRAPH_CACHE_DIR` alone
    relocates only the cache (unit test on `Settings`).
11. An unwritable `home_dir` or `runs_dir` stops the command at startup with a message naming the
    setting, before any work (unit test).
12. Acquired source (git URL or zip) is outside both the run directory and `home_dir`, and is gone when
    the command ends (integration test).
13. After an LLM-enabled run, `analysis/graph.json` contains no `projectOverview` and is byte-identical to
    the graph of an `--ast-only` run of the same corpus; the synthesis is in
    `analysis/corpus-synthesis.json` (integration test — FR-34 AC-3).
14. Pass 2 writes only `analysis/corpus-synthesis.json`; `analysis/llm-annotations.json` is
    byte-identical before and after Pass 2 (unit test).
15. `codeograph run <source> <dir>` where `<dir>` holds files but no manifest or history — including a
    folder holding only `.git` — is refused with status 3 and nothing is written (integration test).
16. `<name>` derivation: a folder named `CON` gives `_CON`; spaces and non-ASCII characters become `-`;
    a name longer than 40 characters is cut (unit test).
17. On Windows without long-path support, a render whose paths would exceed 260 characters fails before
    writing, naming `runs_dir` and `--source-out` (unit test).
18. `eval report` writes nothing inside the run directories it reads; with `--output <file>` it writes
    that file (integration test).

## Pros and Cons of the Considered Options

### Fork 1 — Output locations

**(c) Two outputs. ✅ Chosen.**
* Good, because the user puts the project anywhere without moving the metadata (FR-3 AC-3).
* Good, because every artefact other than the project shares one root, so pointers resolve (FR-27 AC-1).
* Good, because the default keeps both together for the common case.
* Bad, because the manifest may point outside its own directory, so a copied run directory can lose the
  link to a relocated project.

**(a) One root for everything.**
* Good, because the run directory is fully self-contained.
* Good, because every pointer is relative.
* Bad, because a user who wants the project in their own repository must copy it out after every render.

**(b) Two independent roots, both required.**
* Good, because it is what ships, so no code changes.
* Good, because the project folder is always the user's choice.
* Bad, because nothing reconciles the two roots — the compile-check record and its pointer already live
  apart.
* Bad, because no requirement or recorded decision chose it.

**(d) The user's folder is the project; metadata beside it.**
* Good, because the project location is always explicit.
* Good, because one flag covers the common case.
* Bad, because a second target needs a second folder and the metadata no longer has one home.

### Fork 2 — Choosing the run directory

**(d) `./codeograph-out/<name>-<id>/`, configurable. ✅ Chosen.**
* Good, because the output is visible beside the user's work.
* Good, because `runs_dir` makes a fixed location one setting away.
* Good, because the same source re-runs into the same directory with no flag.
* Bad, because the default can sit inside the analysed project, which needs two protections and still
  leaves Docker contexts and editor indexing uncovered.

**(a) Always required.**
* Good, because the user always knows where output goes.
* Good, because it needs no protections.
* Bad, because every first run needs a decision the tool could make.

**(b) Hidden folder under home.**
* Good, because nothing lands in the user's project.
* Good, because one source's history stays in one place whichever directory it is run from.
* Bad, because the deliverable is hidden — the convention reserves hidden home folders for tool state.

**(c) Visible folder under home.**
* Good, because nothing lands in the user's project, and the output is visible.
* Good, because history stays together across working directories.
* Bad, because in CI and containers the home folder is often shared or discarded, while the working
  directory is the job's own.

### Fork 3 — Target folder naming and composition

**(c) `<target>-source/` default, composed by the CLI. ✅ Chosen.**
* Good, because every directory is named for what it contains.
* Good, because renderers stay unaware of placement, so a new renderer cannot get it wrong.
* Bad, because target folders are not grouped in a listing.

**(a) Bare target name.**
* Good, because it is the shortest path.
* Good, because it matches the compile check's existing assumption.
* Bad, because the tool's own namespaces and arbitrary target names share one level.

**(b) A `target/` container.**
* Good, because all projects sit under one prefix.
* Good, because a second target adds no new root entry.
* Bad, because *target* means the build-output root to this audience.
* Bad, because it adds a level for every user to serve the multi-target case.

### Fork 4 — Namespaces

**(b) Everything namespaced; the root holds only index files. ✅ Chosen.**
* Good, because each directory names what it holds, so ownership is expressible per file.
* Good, because a reader finds the manifest first.
* Bad, because every artefact path changes, along with committed examples, goldens and docs.

**(a) Status quo.**
* Good, because it costs nothing.
* Good, because existing consumers keep working.
* Bad, because the root mixes bare artefacts and namespaces with no rule.

**(c) Full symmetry including the manifest.**
* Good, because the rule has no exception.
* Good, because the root becomes a list of namespaces only.
* Bad, because every consumer resolves the manifest at the root.

### Fork 5 — Outside a run

**(a) Three classes by one rule. ✅ Chosen.**
* Good, because the cache's purpose makes any per-run placement non-functional.
* Good, because one question places every future output.
* Good, because it corrects telemetry's accidental nesting inside the cache.
* Bad, because a run directory alone no longer holds everything needed to diagnose a run — the
  invocation id is what joins it to telemetry.

**(b) Everything inside the run.**
* Good, because a run directory is fully self-contained.
* Good, because deleting a run removes all its traces.
* Bad, because the response cache could never hit across runs.

**(c) Both.**
* Good, because each place gets what it needs.
* Good, because a run directory stays self-describing.
* Bad, because every record is written twice and the copies can disagree.

**(d) Two classes only.**
* Good, because the rule is shorter.
* Good, because temporary files are rare.
* Bad, because acquired source has no stated home, so its cleanup has no rule to follow.

### Fork 6 — Render's records

**(a) The run's `evals/`. ✅ Chosen.**
* Good, because evaluation inputs and outputs are in one place, which is where `eval` looks.
* Good, because the project contains nothing of the tool's.
* Bad, because `evals/` has two writers, so ownership must be per file.

**(b) Inside the project.**
* Good, because render would own one contiguous tree.
* Good, because the records travel with the project.
* Bad, because the records would be committed with the user's application.

**(c) A `render/` namespace.**
* Good, because every namespace has exactly one writer.
* Good, because render's records are easy to find.
* Bad, because `eval` reads both namespaces to do one job, and the layout gains a directory.

### Fork 7 — Corpus synthesis

**(b) Its own artefact. ✅ Chosen.**
* Good, because each pass owns exactly one file.
* Good, because a failed synthesis is one missing artefact beside intact annotations.
* Bad, because it adds an artefact, a manifest entry and a schema.

**(a) Inside the annotations file.**
* Good, because enrichment stays one artefact.
* Good, because the annotations schema already has an object envelope to hold it.
* Bad, because Pass 2 would rewrite Pass 1's file — the pattern that broke the graph.

**(c) In the graph.**
* Good, because nothing changes.
* Good, because consumers find the overview with the graph.
* Bad, because FR-34 AC-1 forbids it, and it breaks FR-34 AC-3, NFR-6 and the graph's integrity hash on
  every LLM-enabled run.

## More Information

### Relationships

* **ADR-022** (run manifest and structured logging) — **Fork 5 is superseded by this ADR.** Its logging
  forks remain in force. ADR-022 stays `accepted`; its index entry gains a Fork 5 note.
* **ADR-028** (what a command may overwrite, delete or refuse) — applies its rules to this ADR's
  ownership table; owns `archive/` and `.locks/`.
* **ADR-030** (invocation identity and history) — owns `runs.jsonl` and the per-invocation log files.
* **ADR-031** (command outcomes and consent) — the exit statuses for every refusal named here.
* **ADR-025** (manifest schema) — amended for the new entries this layout creates: the synthesis
  artefact, each target's file list and project location, and the per-section writers.
* **ADR-006** (graph schema) — loses `projectOverview` (Fork 7).
* **ADR-008** (renderer interface) — unchanged; Fork 3 keeps renderers unaware of placement.
* **ADR-015** (telemetry and response cache) — placement corrected (Fork 5); its "self-contained run
  directory" driver is overtaken.
* **ADR-017** (evaluation framework) — finds targets from the manifest; reads render's records from
  `evals/`; decides the render-audit contents with ADR-010.
* **ADR-010** (Spring to NestJS mapping) — its render audit moves from the manifest to
  `evals/render-audit.<target>.json` (Fork 6); contents decided with ADR-017.
* **ADR-001** (project skeleton) — `home_dir` and `runs_dir` follow its setting-name rule.
* **ADR-026** (release versioning) — decides the version consequences of the path changes and the graph
  schema change.

### Requirements touched

* **FR-3 AC-3** — a user-chosen or documented-default project location (Forks 1, 2, 3).
* **FR-27 AC-1, AC-2** — artefacts in the output directory except the rendered source; a run directory
  that is the working directory or an ancestor is refused (Fork 1).
* **FR-20 AC-1, AC-2** — the manifest and logs are in the output directory (Fork 4).
* **FR-29 AC-5** — acquired source is temporary (Fork 5).
* **FR-30 AC-2, AC-4** — discovery skips run directories and reports the skip (Fork 2).
* **FR-34, NFR-6** — the graph holds no LLM output (Fork 7).
* **FR-35 AC-1** — a failed synthesis costs one artefact, not the annotations (Fork 7).
* **FR-38 AC-1, AC-2** — `runs_dir` and `home_dir` are settings; misconfiguration fails at startup
  (Forks 2, 5).
* **FR-16 AC-2** — telemetry stays a separate record, under `home_dir` (Fork 5).
* **NFR-5 AC-1** — renderers stay unaware of placement (Fork 3).

### References

* Requirements — `docs/requirements.md` (FR-3, FR-16, FR-20, FR-27, FR-29, FR-30, FR-34, FR-35, FR-38,
  NFR-5, NFR-6, NFR-7; glossary *Output directory*).
* Maven — [Introduction to the standard directory layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html).
* Cargo — [Build cache](https://doc.rust-lang.org/cargo/reference/build-cache.html).
* dbt — [`target-path`](https://docs.getdbt.com/reference/project-configs/target-path).

### Deferred

* **Log rotation** — still deferred (ADR-022); `logs/` already holds one file per invocation.
* **The render-audit contents** — decided with ADR-017 and ADR-010.

### Open questions

* None recorded at stage 1. The cluster's design review adds any it raises.
