---
status: proposed
date: 2026-10-31
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-030 — Invocation Identity and History

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `bd6a837` (2026-10-31). File and
line references are to that commit.

**ADR-022 Fork 3** fixed the run identifier's format — a UTC timestamp plus a six-character random
suffix — and FR-20 AC-3 requires one correlation identifier to join the manifest, the logs and the
telemetry. **Which identifier each command uses was never decided, and the three commands disagree:**

| Command | Identifier it uses | Evidence |
|---|---|---|
| `run` | Generates its own | `cli/main.py:261` |
| `render` | Generates its own, with **no link** to the run whose graph it rendered | `cli/render_pipeline.py:87` |
| `eval` | **Reuses the run's**, read from the manifest | `evals/runner.py:119` |

So a render's telemetry cannot be joined to the run it rendered, and an evaluation's records are
indistinguishable from the run's own.

**Only `run` writes a log file** (`<out>/logs.jsonl`, `logging_config.py:121`). `render` and `eval` accept
the verbosity flags, but their file output never engages.

**Nothing records the history of a directory.** The manifest describes the current state; once a later
command replaces an output, nothing says what was there, which command produced it, or whether an
earlier command finished.

**The requirements** ask that every invocation be recorded with its command, its outcome,
the invocation it built on, what it produced and what it superseded; that an unfinished invocation be
distinguishable; and that the history be viewable without an external service (FR-43). The run directory
is reused by every command against a run (glossary, *Output directory*), and superseded output is kept
(FR-42) — so a directory accumulates a history that has to be legible.

**This ADR decides how each invocation is identified, how the history is kept, and where each
invocation logs.** It is one of four coupled decisions:

| ADR | Decides |
|---|---|
| ADR-029 | Where each output lives, and which command writes it |
| ADR-028 | What a command may overwrite, delete or refuse |
| **ADR-030** (this) | How each invocation is identified, and how the history of a run directory is kept |
| ADR-031 | How every command reports its outcome and asks for consent |

## Decision Drivers

* **Visibility of every run** — every invocation against a directory, and its outcome, can be found
  (FR-43 AC-1).
* **One join key per record** — any manifest entry, log line or telemetry record leads to the invocation
  that wrote it (FR-20 AC-3).
* **The manifest stays about the present** — history lives beside it, not inside it.
* **An interrupted invocation is visible as unfinished** (FR-43 AC-2).
* **No external service required** — everything is inspectable locally (FR-43 AC-3).

## Considered Options

### Fork 1 — Identity across commands

* (a) Every command reuses the identifier of the `run` that created the directory.
* **(b) Every invocation gets its own identifier and records the identifier of the run it built on. ✅**
* (c) Every invocation gets its own identifier, with no link.

### Fork 2 — Where the history of a run directory is kept

* (a) Nowhere — the manifest describes the present only (the shipped behaviour).
* (b) A list of invocations inside the manifest.
* **(c) A separate append-only history file, `runs.jsonl`, with a `history` command to show it. ✅**
* (d) Reconstructed from the log files on demand.

### Fork 3 — Where each invocation logs

* (a) One log file per run directory that every command appends to, with a field naming the command.
* **(b) One log file per invocation, `logs/<invocation id>.jsonl`. ✅**
* (c) Only `run` logs to a file (the shipped behaviour).

## Decision Outcome

### Fork 1 — Own identifier, recorded parent: (b)

**Every invocation generates its own identifier at start** — `run`, `render`, `eval`, `eval report`,
`purge` and `history` alike — in ADR-022 Fork 3's format. It is a glossary *Invocation*, and
its records are its own.

**It records the identifier of the run it built on (its *parent*):** the `run` invocation whose analysis
it read — for `render` and `eval`, the `run` recorded in the manifest when they start. A `run` has no
parent. Finer lineage — exactly which artefacts an output was built from — is carried by the input
fingerprints each artefact records (ADR-025 amendment), so the parent does not need to name more than
one invocation.

**The join FR-20 AC-3 requires holds through one identifier per record:**

| Record | Carries |
|---|---|
| A manifest entry | the identifier of the invocation that produced it (ADR-025 amendment) |
| A log line | its invocation's identifier; the file is named by it (Fork 3) |
| A telemetry record | its invocation's identifier (ADR-015) |
| An archive folder | the identifier of the invocation that archived it (ADR-028) |
| A history entry | the identifier and its parent (Fork 2) |

### Fork 2 — `runs.jsonl` and `history`: (c)

**`<run directory>/runs.jsonl`** (placed by ADR-029) — one JSON object per line, append-only, with its
own `schema_version`. **Two entries per invocation:**

| Entry | Written | Holds |
|---|---|---|
| `started` | when the invocation begins | identifier · parent · command · the options given on the command line · start time (UTC) · codeograph version |
| `finished` | when it ends, whatever the result | identifier · end time · outcome · what it produced · what it superseded and archived · for `purge`, what it removed |

- **Outcome** is one of ADR-031's five classes — success, failure, completed with recorded failures,
  refused, quality gate failed — the same class as the exit status.
- **A `started` entry with no `finished` entry is an invocation that did not finish** (FR-43 AC-2) —
  crashed, killed, or still running. A refused invocation still writes both: refusing changes no artefact
  and no superseded output (FR-45 AC-2), and the history is a diagnostic record, not an artefact.
- **No secret is ever recorded.** A source location carrying credentials is refused before anything is
  written (ADR-002 amendment); credentials otherwise come only from the environment (FR-38 AC-3); and
  every recorded value passes through credential stripping as a defence in depth.
- **Entries are appended under ADR-028's brief lock**, so concurrent invocations never interleave a line.
- **The history is never archived or rewritten.** `purge` appends its own entry naming the archive
  folders it removed; `history` shows them as purged.
- **Every invocation is recorded** (FR-43 AC-1), read-only ones included:
  - `eval report` appends its entries **to each run directory it reads**, naming where its report went;
  - `history` records itself; when the run directory cannot be written (a committed example, a read-only
    mount), its entries go to a fallback history under `<home_dir>/history/`, keyed by the run
    directory's identity, and `history` says so;
  - **`history` hides its own entries by default** (`--all` shows them), so viewing does not drown the
    record.
- **A recovery is recorded** (ADR-028 Fork 5): the invocation that rolls back an unfinished one appends an
  entry naming it and what was undone.
- **A truncated last line** — from a crash mid-append — is skipped and reported by readers; writers write
  each line and its newline in one call.

**The manifest stays about the present.** A history inside it (b) would grow with every invocation, and
every writer would rewrite the whole list to append one line — the lost-update hazard ADR-028 guards
against, made routine.

```
codeograph history <run directory>          ← one line per invocation, newest first
codeograph history <run directory> --all    ← including history's own entries
codeograph history <run directory> --json   ← the raw entries
```

It reads only the local file (FR-43 AC-3).

### Fork 3 — One log file per invocation: (b)

```
<run directory>/logs/<invocation id>.jsonl
```

**Every invocation that writes to a run directory logs to its own file.** The record format is
ADR-022 Fork 4's, unchanged; the file name is the invocation's identifier, so no field naming the
command is needed — the history says which command it was.

**One file per invocation, not one shared file** (a): concurrent invocations never interleave lines in one
file, a log is never appended to by a later command, and an invocation's log can be read on its own.

**Logs are kept with the history.** They are diagnostic records, not superseded output, so nothing
archives them; retention is deferred with log rotation (ADR-022).

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-002
A source location carrying credentials is refused at acquisition, so the history never receives one.

#### Constraint flagged for ADR-022
**Fork 3 is amended:** every invocation generates its own identifier at start, in the existing format,
and records its parent. **Forks 4–6 are unchanged**; the log file's location becomes
`logs/<invocation id>.jsonl` (with ADR-029, which supersedes Fork 5).

#### Constraint flagged for ADR-025
Every manifest entry records the identifier of the invocation that produced it.

#### Constraint flagged for ADR-015
Each invocation's telemetry records carry that invocation's identifier, and its telemetry file is named by
it — for `render` as for `run`.

#### Constraint flagged for ADR-031
The outcome recorded in the history uses the same five classes as the exit statuses.

## Consequences

**Positive.**
1. Every record joins to the invocation that wrote it.
2. A run directory's history is one command away, without opening any file.
3. An interrupted invocation is visible as unfinished.
4. `render` and `eval` gain log files, matching the verbosity flags they already accept.
5. One identity rule replaces three inconsistent behaviours.

**Negative.**
1. The history and the log files grow without bound until log rotation exists.
2. Every invocation writes two history entries and a log file.
3. One run's work spans several identifiers; grouping them needs the history. An evaluation's records no
   longer carry the run's identifier, so a reader that relied on it changes.

## Confirmation

1. `run`, `render` and `eval` against one run directory produce three different identifiers; the
   `render` and `eval` history entries name the `run` as parent (integration test).
2. A `render`'s telemetry records, its log file name and its manifest entry all carry the same identifier,
   and that identifier's history entry names the `run` it rendered (integration test — FR-20 AC-3).
3. After `run`, `render` and `eval`, `runs.jsonl` holds six entries — `started` and `finished` for each —
   with outcome `success` (integration test).
4. Killing an invocation after it starts leaves a `started` entry with no `finished` entry, and `history`
   marks it as not finished (fault-injection test).
5. A refused invocation writes both entries, with outcome `refused`, and changes no artefact (integration
   test).
6. Two invocations running at once produce whole, non-interleaved lines in `runs.jsonl` and two separate
   log files (concurrency test).
7. `purge` appends an entry naming the archive folders it removed; earlier entries are byte-identical
   before and after (integration test).
8. No history entry contains the value of any credential setting, with credentials set in the environment
   (unit test).
9. `render -v` and `eval -v` each write `logs/<their identifier>.jsonl` (integration test).
10. `codeograph history <run directory>` works with no network access and lists every invocation, newest
    first (integration test).
11. `history` appends its own entries and hides them unless `--all`; on a read-only run directory its
    entries go to `<home_dir>/history/` and it says so (integration test).
12. `eval report` over two run directories appends its entries to both (integration test).
13. A history file whose last line is truncated is read without error, and the truncation is reported
    (unit test).
14. The outcome field takes each of the five classes, always matching the exit status (unit test).
15. A source URL carrying a token is refused before any history entry is written (integration test).

## Pros and Cons of the Considered Options

### Fork 1 — Identity

**(b) Own identifier, recorded parent. ✅ Chosen.**
* Good, because every record names the invocation that wrote it, matching the glossary's *Invocation*.
* Good, because the parent keeps the join to the run (FR-20 AC-3).
* Good, because one rule replaces the three behaviours that ship.
* Bad, because a reader sees several identifiers for one run's work, and needs the history to group them.

**(a) Reuse the run's identifier.**
* Good, because one identifier covers a run's whole history.
* Good, because grouping needs no lookup.
* Bad, because a render's or an evaluation's records cannot be told apart from the run's, and two
  invocations of the same command collide.

**(c) Own identifier, no link.**
* Good, because it is the simplest rule.
* Good, because every record is distinct.
* Bad, because nothing joins a render to its run, which breaks FR-20 AC-3.

### Fork 2 — History

**(c) `runs.jsonl` and `history`. ✅ Chosen.**
* Good, because appending one line never rewrites earlier entries.
* Good, because the manifest stays about the present.
* Good, because a missing `finished` entry shows an unfinished invocation with no extra mechanism.
* Bad, because it is one more file, and it grows with every invocation.

**(a) No history.**
* Good, because there is nothing to build.
* Good, because the directory holds less.
* Bad, because FR-43 cannot be met, and an archive folder has no record of why it exists.

**(b) Inside the manifest.**
* Good, because one file holds everything.
* Good, because the manifest's existing validation covers it.
* Bad, because every writer rewrites the whole history to add one entry, and the manifest grows without
  bound.

**(d) Reconstructed from logs.**
* Good, because no new file is written.
* Good, because the logs already hold the detail.
* Bad, because an invocation that crashed before logging leaves no trace, and the outcome and what was
  archived are not reliably in any log line.

### Fork 3 — Logs

**(b) One file per invocation. ✅ Chosen.**
* Good, because concurrent invocations never interleave.
* Good, because a log is never appended to by a later command.
* Bad, because the number of log files grows with every invocation.

**(a) One shared file.**
* Good, because one file holds a run directory's whole log.
* Good, because the file count stays fixed.
* Bad, because concurrent writers interleave, and every record needs a field naming the command.

**(c) Only `run` logs to a file.**
* Good, because it ships.
* Good, because it writes the fewest files.
* Bad, because `render` and `eval` accept the verbosity flags with no file output, contradicting ADR-022
  Fork 6's same-flags-everywhere decision.

## More Information

### Relationships

* **ADR-022** (run manifest and structured logging) — Fork 3 amended (each invocation's own identifier and
  parent); Forks 4 and 6 unchanged.
* **ADR-029** (output layout and ownership) — places `runs.jsonl` and `logs/`.
* **ADR-028** (what a command may overwrite, delete or refuse) — names archive folders by invocation
  identifier; supplies the brief lock the history is appended under.
* **ADR-031** (command outcomes and consent) — the outcome classes recorded here.
* **ADR-025** (manifest schema) — amended so every entry records its producing invocation.
* **ADR-015** (telemetry and response cache) — telemetry carries each invocation's identifier.
* **ADR-002** (input-agnostic design) — amended: credentials never travel in a source location; acquisition
  never prompts.

### Requirements touched

* **FR-20 AC-2, AC-3** — every invocation logs; one identifier per record joins manifest, logs and
  telemetry (Forks 1, 3).
* **FR-43 AC-1, AC-2, AC-3** — every invocation recorded; unfinished ones visible; viewable locally
  (Fork 2).
* **FR-45 AC-2** — a refused invocation changes no artefact; its history entries are diagnostic records.
* **FR-38 AC-3** — no secret enters the history.

### References

* Requirements — `docs/requirements.md` (FR-20, FR-38, FR-43, FR-45; glossary *Invocation*,
  *Diagnostic record*).

### Deferred

* **Retention of logs and history** — with log rotation (ADR-022).

### Open questions

* None recorded at stage 1. The cluster's design review adds any it raises.
