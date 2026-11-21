---
status: proposed
date: 2026-11-19
decision-makers: gvsambhu
consulted: AI design advisor
informed: future contributors
---

# ADR-030 — Invocation Identity and History

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0 (2026-10-31).

**ADR-022 Fork 3** fixed the run identifier's format — a UTC timestamp plus a six-character random
suffix — and FR-20 AC-3 requires one correlation identifier to join the manifest, the logs and the
telemetry. **Which identifier each command uses was never decided, and the three commands disagree:**

| Command | Identifier it uses |
|---|---|
| `run` | Generates its own |
| `render` | Generates its own, with **no link** to the run whose graph it rendered |
| `eval` | **Reuses the run's**, read from the manifest |

So a render's telemetry cannot be joined to the run it rendered, and an evaluation's records are
indistinguishable from the run's own.

**Only `run` writes a log file** (`<out>/logs.jsonl`). `render` and `eval` accept
the verbosity flags, but their file output never engages.

**Nothing records the history of a directory.** The manifest describes the current state; once a later
command replaces an output, nothing says what was there, which command produced it, or whether an
earlier command finished.

**The requirements** ask that every invocation be recorded with its command, its outcome,
the invocation it built on, what it produced and what it superseded; that an interrupted invocation be
distinguishable from one that finished and from one still running; and that the history be viewable
without an external service (FR-43). The run directory
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
* **An interrupted invocation is told apart** from one that finished and from one still running
  (FR-43 AC-2).
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

### Fork 4 — How `history` tells an interrupted invocation from one still running

* **(a) The `started` entry records the process; `history` checks whether it is still alive. ✅**
* (b) `history` checks whether the invocation still holds an ADR-028 claim.
* (c) A running invocation refreshes a heartbeat; one older than a threshold counts as interrupted.

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
| `started` | when the invocation begins | identifier · parent · command · the options given on the command line · start time (UTC) · codeograph version · the holder identity ADR-028 Fork 4 defines — host, process-id space, process id and the process's start time (Fork 4) |
| `finished` | when it ends, whatever its outcome | identifier · end time · outcome · what it produced · what it superseded and archived · for `purge`, what it removed · for an invocation that called an LLM, its LLM totals |

- **Outcome** is one of the five exit statuses ADR-031 assigns — success, failure, completed with
  recorded failures, refused, quality gate failed — the same as the invocation's exit status. Exit 130,
  for an interrupt, is never written: an interrupted invocation leaves no `finished` entry, and `history`
  derives it (Fork 4).
- **A `started` entry with no `finished` entry is an invocation that has not finished** — still running,
  or interrupted (Ctrl-C, killed, crashed); Fork 4 tells the two apart (FR-43 AC-2). A refused invocation
  still writes both entries: refusing changes no artefact and no superseded output (FR-45 AC-2), and the
  history is a diagnostic record, not an artefact.
- **An invocation's LLM totals live in its `finished` entry** (FR-16 AC-3): the requests it made,
  counted by FR-16 AC-1's three kinds — answered by the provider, answered from the cache, failed — its
  input and output tokens, and its cost. A call whose route has no price carries no cost, and the total
  is then marked unavailable, never `$0` — ADR-027 Fork 4's rule for an unknown price. The manifest keeps
  its present-tense aggregates (ADR-015, ADR-025); the history is where every invocation's totals stay,
  including one whose outputs a later invocation superseded.
- **An interrupted invocation's totals are derived.** It writes no `finished` entry, so `history` sums
  its telemetry records, which carry its identifier (ADR-015), and shows the totals marked *derived*; when
  that telemetry is not on this machine, they are shown as unavailable.
- **No secret is ever recorded.** A source location carrying credentials is refused before anything is
  written (ADR-002 amendment); credentials otherwise come only from the environment (FR-38 AC-3) and
  never reach any record (FR-38 AC-5); and every recorded value passes through credential stripping
  as a defence in depth.
- **Entries are appended under ADR-028's brief lock**, so concurrent invocations never interleave a line.
- **The history is never archived or rewritten.** `purge` appends its own entry naming the archive
  folders it removed; `history` shows them as purged.
- **Every invocation is recorded** (FR-43 AC-1), read-only ones included:
  - `eval report` appends its entries **to each run directory it reads**, naming where its report went;
  - `history` records itself; when the run directory cannot be written (a committed example, a read-only
    mount), its entries go to a fallback history under `<home_dir>/history/`, keyed by the run
    directory's identity, and `history` says so;
  - **`history` hides its own entries by default** (`--all` shows them), so viewing does not drown the
    record — except a recovery entry, which is always shown.
- **A recovery is recorded** (ADR-028 Fork 5): the invocation that rolls back an unfinished one appends an
  entry naming it and what was undone. `history` shows a recovery entry whichever command wrote it,
  `history` itself included.
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

### Fork 4 — The recorded process, checked for liveness: (a)

**The `started` entry records the holder identity ADR-028 Fork 4 defines** — the host, the process-id
space, the process id and the process's start time. For an entry with no `finished` entry, `history`
applies ADR-028 Fork 4's stale test to it:

| Where the invocation started | Its process | `history` shows |
|---|---|---|
| This host and process-id space | Alive, with the recorded start time | **running** |
| This host and process-id space | Gone, or the id now belongs to a process with another start time | **interrupted** |
| This host and process-id space | Gone, and a later invocation rolled it back (ADR-028 Fork 5) | **interrupted — recovered by** the recovering invocation's identifier |
| Another host, another process-id space, or an earlier boot of this machine | — | **not finished — started where its process cannot be checked, cannot tell** |

**The start time defeats a reused process id**: an id that now names a different process is not taken for
the original. **Another host or process-id space is reported, not guessed** — ADR-028 refuses a claim
from one for the same reason, and lets `history`, which publishes nothing, proceed past a journal from
one (ADR-028 Fork 5). **A restart reads the same way**: the boot session is part of the recorded
process-id space (ADR-028 Fork 4), so an invocation a restart killed shows as *cannot tell*. FR-43 AC-2
is therefore met for an interruption within one boot; a restart is the stated exception. Windows and WSL
on one machine share a host name but not process ids, which
is why the process-id space is compared too.

**A `finished` entry is final.** A journal its invocation left behind is deleted without a roll-back
(ADR-028 Fork 5), so no recovery ever names a finished invocation.

**The check covers every invocation, read-only ones included.** `history` and `eval report` take no claim,
so a claim-based check (b) would show a running `eval report` as interrupted. **No heartbeat** (c): it
would cover the cases this check reports as *cannot tell* — another host, another process-id space such
as Windows and WSL on one machine, and an earlier boot — but it writes throughout the run, needs a threshold with no
cited basis, is a second liveness rule beside ADR-028's, and leaves a window in which a dead invocation
still looks alive.

**`history --json` returns the derived state beside the raw entries**, so a script reads the same
answer a person sees.

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
it — for `render` as for `run` — so an interrupted invocation's totals can be derived from them (Fork 2).
A call whose route has no price records no cost, rather than a cost of zero.

#### Constraint flagged for ADR-031
The outcome recorded in the history is one of the five exit statuses; exit 130, for an interrupt, is
derived by `history`, never written (Fork 4).

## Consequences

**Positive.**
1. Every record joins to the invocation that wrote it.
2. A run directory's history is one command away, without opening any file.
3. An interrupted invocation is shown as interrupted — distinct from a finished one and from one still
   running — for every command, read-only ones included.
4. `render` and `eval` gain log files, matching the verbosity flags they already accept.
5. One identity rule replaces three inconsistent behaviours.

**Negative.**
1. The history and the log files grow without bound until log rotation exists.
2. Every invocation writes two history entries and a log file.
3. One run's work spans several identifiers; grouping them needs the history. An evaluation's records no
   longer carry the run's identifier, so a reader that relied on it changes.
4. For an invocation started on another host or in another process-id space — the other shell on the same
   machine included — or before the machine last restarted, `history` cannot say whether it is running or
   interrupted.

## Confirmation

1. `run`, `render` and `eval` against one run directory produce three different identifiers; the
   `render` and `eval` history entries name the `run` as parent (integration test).
2. A `render`'s telemetry records, its log file name and its manifest entry all carry the same identifier,
   and that identifier's history entry names the `run` it rendered (integration test — FR-20 AC-3).
3. After `run`, `render` and `eval`, `runs.jsonl` holds six entries — `started` and `finished` for each —
   with outcome `success` (integration test).
4. Killing an invocation before its recovery journal is written (ADR-028 Fork 1, step 4) leaves a
   `started` entry with no `finished` entry, and `history` shows it as interrupted. Killing one after the
   journal is written, then running `history`, shows it as interrupted and recovered by that `history`
   invocation, without `--all` (fault-injection test).
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
14. The outcome field takes each of the five exit statuses, always matching the invocation's, and never
    *interrupted* (unit test).
15. A source URL carrying a token is refused before any history entry is written (integration test).
16. `history` run while a `render` and an `eval report` are still running shows both as running; a
    `started` entry whose process id now belongs to a process with another start time shows as
    interrupted; one recording another host, another process-id space or an earlier boot session shows as
    *cannot tell* (integration and unit tests).
17. Two `render` invocations against one run each record their own LLM totals in their `finished`
    entries, and the second does not change the first's (integration test — FR-16 AC-3).
18. An interrupted `run` shows LLM totals marked *derived*, equal to the sums of its telemetry records
    (fault-injection test).
19. An invocation in which one call's route has no price records its total cost as unavailable, not `0`
    (unit test).
20. No `runs.jsonl` entry contains the host's name; a `started` entry holds its one-way hash (unit test).

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

### Fork 4 — Running or interrupted

**(a) The recorded process, checked for liveness. ✅ Chosen.**
* Good, because it covers every invocation, read-only ones included.
* Good, because it is the same liveness test ADR-028 applies to a stale claim — one rule, not two.
* Good, because recording the process's start time defeats a reused process id.
* Bad, because an invocation started on another host or in another process-id space is reported as
  *cannot tell*.
* Bad, because every `started` entry carries four more fields.

**(b) A claim still held.**
* Good, because it reuses state ADR-028 already keeps, and adds no field.
* Bad, because read-only invocations take no claim, so a running `history` or `eval report` shows as
  interrupted — FR-43 AC-2 is not met for them.
* Bad, because `history` comes to depend on ADR-028's lock layout.

**(c) A heartbeat.**
* Good, because it works across hosts.
* Bad, because a running invocation writes throughout, and the staleness threshold needs a cited basis.
* Bad, because until the threshold passes a dead invocation still looks alive.
* Bad, because it is a second liveness rule beside ADR-028's.

## More Information

### Relationships

* **ADR-022** (run manifest and structured logging) — Fork 3 amended (each invocation's own identifier and
  parent); Forks 4 and 6 unchanged.
* **ADR-029** (output layout and ownership) — places `runs.jsonl` and `logs/`.
* **ADR-028** (what a command may overwrite, delete or refuse) — names archive folders by invocation
  identifier; supplies the brief lock the history is appended under, and the liveness test Fork 4 reuses.
* **ADR-031** (command outcomes and consent) — the outcome classes recorded here.
* **ADR-025** (manifest schema) — amended so every entry records its producing invocation.
* **ADR-015** (telemetry and response cache) — telemetry carries each invocation's identifier.
* **ADR-002** (input-agnostic design) — amended: credentials never travel in a source location; acquisition
  never prompts.

### Requirements touched

* **FR-16 AC-3** — each invocation that called an LLM records its totals (Fork 2).
* **FR-20 AC-2, AC-3** — every invocation logs; one identifier per record joins manifest, logs and
  telemetry (Forks 1, 3).
* **FR-43 AC-1, AC-2, AC-3** — every invocation recorded; an interrupted one told apart from a finished
  one and from one still running; viewable locally (Forks 2, 4).
* **FR-45 AC-2** — a refused invocation changes no artefact; its history entries are diagnostic records.
* **FR-38 AC-3, AC-5** — secrets come only from the environment, and none enters the history.

### References

* Requirements — `docs/requirements.md` (FR-20, FR-38, FR-43, FR-45; glossary *Invocation*,
  *Diagnostic record*).

### Deferred

* **Retention of logs and history** — with log rotation (ADR-022).

### Open questions

* None recorded at stage 1. The cluster's design review adds any it raises.

## Revision history

* **2026-11-10** — Fork 4 added: `history` tells an interrupted invocation from one still running by
  checking, on the same host, whether the process recorded in the `started` entry is alive — ADR-028's
  stale-claim test; for another host it reports that it cannot tell. The `started` entry gains the host
  and the process identity, and the outcome field is stated as five completion classes, with
  *interrupted* derived. Exposed by a requirements revision: FR-43 AC-2 now asks that an interrupted
  invocation be distinguishable from one still running, which a missing `finished` entry alone cannot
  show.
* **2026-11-11** — The `finished` entry gains the invocation's LLM totals — calls, tokens and cost — so
  each invocation's totals survive a later one that supersedes its outputs; the manifest keeps its
  present-tense aggregates. Exposed by a requirements revision: FR-16 AC-3 now asks that each invocation
  that called an LLM record its totals, which a per-pass manifest aggregate cannot keep for two `render`
  invocations.
* **2026-11-12** — Fork 4 records the holder identity ADR-028 Fork 4 defines — the host as a one-way
  hash, the process-id space, the process id and its start time — and applies ADR-028's stale test in
  place of a same-host check; a `finished` entry is final, so no recovery names a finished invocation.
  The `finished` entry counts requests by FR-16 AC-1's three kinds, an unpriced call makes the cost
  unavailable (ADR-027 Fork 4), and an interrupted invocation's totals are derived from its telemetry.
  Exposed by the design review of the 2026-11-10 and 2026-11-11 changes: the liveness test was unstated,
  a reused process id or the other shell on one machine could be taken for the holder, and an interrupted
  invocation's totals were lost.
* **2026-11-18** — The outcome is stated in ADR-031's exit statuses; the heartbeat's rejection and the
  *cannot tell* statements name another process-id space as well as another host; `history` proceeds
  past a journal from another host or space (ADR-028 Fork 5) and always shows a recovery entry; a
  Confirmation item covers the host's hash in `runs.jsonl`. An invocation a restart killed shows as
  *cannot tell* — in the heartbeat's rejection too — and FR-43 AC-2 is stated as met within one boot; Confirmation 4's kill points are set at
  the journal write. Exposed by a verification of the 2026-11-12 change.
* **2026-11-19** — code citations replaced by descriptions of the behaviour; the commit anchor replaced by
  the release the Context describes; no decision changed.
