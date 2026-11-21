---
status: proposed
date: 2026-11-19
decision-makers: gvsambhu
consulted: AI design advisor
informed: future contributors
---

# ADR-028 — What a Command May Overwrite, Delete or Refuse

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0 (2026-10-31).

**Every command that writes output answers a non-empty destination the same way: refuse, or with
`--force`, delete everything in it.** `run` and `render` both prepare their destination through one
shared routine. With `--force`, it removes every file and folder in the destination — whether the tool
wrote it or not.

**That rule fails in both directions:**

- **Too strict for the tool's own output.** Re-running against a previous run's output is refused, so the
  documented multi-pass workflow (`run --ast-only`, then a full `run`, in one directory) cannot be done
  without `--force` — which then deletes the graph the first pass produced.
- **Too loose for everything else.** `--force` is the ordinary way to re-run, and it empties the folder
  regardless of what is in it: a user's edits to a rendered project, files they added, anything placed
  there by mistake. The only guard rejects the working directory and its ancestors; a sibling folder, a
  home folder or another drive is emptied without complaint.
- **Nothing protects concurrent commands.** `render` and `eval` update the manifest by reading, changing
  and rewriting it, with no lock or check; two renders running at once (a CI matrix over targets) can
  silently lose one's entry.
- **An earlier result is gone once replaced.** Nothing keeps the previous graph, scorecard or project, so
  comparing two runs means choosing two folders in advance.

**The requirements state the opposite obligations:** re-running needs no overriding option (FR-27
AC-3); content the tool did not produce is deleted only by a removal the user explicitly requests (AC-4)
and overwritten only with consent (AC-5); a directory from an incompatible earlier version is refused
(AC-6); superseded output is preserved, never removed without the user acting (FR-42); concurrent
invocations never corrupt their outputs (FR-44); and a refused invocation changes nothing (FR-45 AC-2).

**This ADR decides what a command may overwrite, delete or refuse.** It applies its rules to the layout
and the per-file ownership that **ADR-029** defines. It is one of four coupled decisions:

| ADR | Decides |
|---|---|
| ADR-029 | Where each output lives, and which command writes it |
| **ADR-028** (this) | What a command may overwrite, delete or refuse |
| ADR-030 | How each invocation is identified, and how the history of an output directory is kept |
| ADR-031 | How every command reports its outcome and asks for consent |

## Decision Drivers

* **No silent loss** — nothing the user did, and no earlier result, disappears without a command that says
  so (FR-27 AC-4, FR-42).
* **Re-running is the normal path** — it never needs an override (FR-27 AC-3).
* **A folder never misrepresents what is current** — an output built from changed inputs is detected and
  stops being indexed as current (FR-33 AC-6).
* **Safety against corruption** — a crash, a second command running at once, or an edited project never
  leaves the directory inconsistent (FR-44).
* **Visibility of earlier results** — a replaced output stays inspectable until the user removes it.
* **CI never prompts and never corrupts** — an automated run gets a clear refusal it can retry.
* **No silent failures** — an existing folder the tool cannot interpret is refused clearly, never
  half-understood (FR-27 AC-6).

## Considered Options

### Fork 1 — What happens to output a command replaces

* (a) Overwrite in place.
* (b) Delete the superseded output, then write.
* **(c) Move the superseded output to an archive in the run directory, before writing. ✅**
* (d) Never reuse a directory — a fresh one per invocation.

### Fork 2 — Re-rendering over a project that already exists

* (a) Overwrite every file (the shipped `--force`).
* (b) Refuse if any generated file was edited; `--force` overrides.
* (c) Overwrite only unedited files; report the edited ones.
* **(d) One option naming the intent — `--on-existing keep | keep-regenerate-deleted | overwrite-edited |
  clean`, default `keep`; `--force` removed. ✅**

### Fork 3 — An output directory written by an earlier, incompatible version

* (a) Migrate it on read.
* (b) Refuse, and ship a one-off migration command.
* **(c) Refuse with a message stating how to proceed; the remedy is a re-run. ✅**
* (d) Read both layouts indefinitely.

### Fork 4 — Two commands writing one run directory at once

* (a) One lock for the whole command.
* (b) Check that the manifest is unchanged just before writing it.
* **(c) A claim on each folder a command writes, a brief lock around the archive and manifest steps, and
  a check of the inputs before publishing. ✅**
* (d) Document "one command at a time" only.

### Fork 5 — An invocation that did not finish

* **(a) Roll back: a journal of planned moves, written before the first move, lets a failing invocation
  undo its own moves and the next invocation undo a crashed one. ✅**
* (b) Roll forward when possible: as (a), but complete the publish if every new output was fully written.
* (c) Refuse until repaired: the next invocation refuses until an explicit `repair` command rolls back.

## Decision Outcome

### Fork 1 — Archive superseded output: (c)

**An output is superseded** when the command that produces it runs again, or when anything it was built
from has changed — detected by the input fingerprints each artefact records (ADR-025 amendment). A
scorecard built from an older graph is superseded the moment the graph changes, even if no one
re-evaluates. A rendered project depends on the graph **and** the annotations — the render prompt
carries both — so a change of model alone, with the graph unchanged, supersedes it. Everything else stays current, and **nothing is copied when a command only adds outputs**.

**Before writing, the invocation moves what it supersedes into the archive:**

```
<run directory>/archive/<time>-<invocation id>/      ← one folder per superseding invocation
  ├── manifest.json                                  ← the manifest as it was before
  └── …                                              ← each superseded output, at its original relative path
```

- **One sequence, every time** — each step only once the one before has succeeded:
  1. refusal checks and claims (Fork 4);
  2. outputs produced under temporary names — held, not yet published;
  3. the input check (Fork 4);
  4. the recovery journal written (Fork 5), then the superseded outputs moved to the archive — a rename
     within the run directory;
  5. the new outputs published — renamed into place;
  6. the manifest written (ADR-025);
  7. the history's `finished` entry (ADR-030).

  **Every refusal happens before anything moves**, so a refusal changes nothing (FR-45 AC-2). A crash or
  failure after step 4 is rolled back (Fork 5).
- **The archive location is a setting**, `archive_dir` (`CODEOGRAPH_ARCHIVE_DIR`; default
  `<run directory>/archive/`); a path given there is used as given. **On another drive a rename is not atomic**, so the move becomes copy, verify each file's
  hash, delete the originals — and only then are new outputs written. If the copy fails — a full
  disk, a lost drive — its partial archive folder is removed and the originals stay untouched.
- **A file another process holds open** (Windows) stops the move with a message naming the file; nothing
  is written.

**A rendered project is never moved by this rule.** When the graph changes, the project is superseded
but stays where it is; the manifest stops indexing it as current (FR-33 AC-6). It changes only when
`render` runs again, under Fork 2 — which archives every file it replaces.

**Nothing is removed automatically.** The archive's size is reported after each invocation that adds to
it (FR-42 AC-6). Removal is the user's command:

```
codeograph purge <run directory>                 ← everything in the archive
codeograph purge <run directory> --before <date>
codeograph purge <run directory> --keep <n>      ← keep the n most recent archive folders
```

`<date>` is ISO 8601 (`2026-10-31`, or a UTC date-time). **Purge selects archive folders from its own
run directory's history** (ADR-030), never by listing the archive location — several run directories may
share one `archive_dir`, and one must never count or remove another's folders. Purge cannot be undone, so
it asks for consent under ADR-031's rule; the history records what was purged. **This is the one way content the tool did not produce is ever deleted** — an edited
or added file that Fork 2 archived is removed only when the user purges it (FR-27 AC-4).

### Fork 2 — Named re-render modes: (d)

**Each rendered target has a file list** recording every file render produced and its hash (ADR-025
amendment). Comparing it with the folder classifies every file:

| Class | Meaning |
|---|---|
| generated, unchanged | render produced it; its hash still matches |
| generated, edited | render produced it; the user changed it |
| generated, deleted | render produced it; the user removed it |
| user-added | not in the file list |

**One option, four values — each a stance on the user's changes:**

| `--on-existing` | Edited | Deleted generated | User-added | Stance |
|---|---|---|---|---|
| **`keep`** (default) | kept, reported | stay deleted | kept | keeps the user's changes |
| `keep-regenerate-deleted` | kept, reported | regenerated | kept | restores what the user removed by accident |
| `overwrite-edited` | archived, then overwritten | regenerated | kept | takes the generator's version |
| `clean` | archived | regenerated | archived, except what the project's ignore rules cover | starts over, losing nothing |

**Files a new render no longer produces:** unchanged ones are archived; edited ones stay and are reported
as orphans.

**Files the project's own ignore rules cover** — its `.gitignore`: dependency folders such as
`node_modules/`, build output — are never archived or deleted by any mode; `clean` leaves them in place
and reports them. They are regenerable, and archiving them would make the archive large and a cross-drive
move slow.

**A render into a folder that has content but no file list** (a first render, or one whose file list the
tool does not read — ADR-035 Fork 2) — the tool cannot tell its files from the user's — **is refused**,
changing nothing, unless the user names `overwrite-edited` (each existing file the render would write is
archived, then overwritten; others stay) or `clean` (everything archived, fresh render). **Empty means
empty:** a folder holding only `.git` is not empty. The refusal states the consequence of each choice —
how many existing files would be overwritten and which would stay — so the choice is informed.

**`--force` is removed from `run` and `render`.** Re-running needs no override (Fork 1), and every
re-render stance has a name; a flag that means "do something destructive" has nothing left to mean. No
alias is kept.

### Fork 3 — Refuse earlier-version folders; re-run: (c)

**An output directory from an incompatible earlier version** is recognised by its shape — a bare
`graph.json` at the root and no invocation history. It is **refused before anything is written**, with a
message that the folder is untouched and the exact command that re-creates it in the current layout.

**A re-run is cheap by construction:** the graph is byte-identical for the same corpus within the
execution envelope (NFR-6), and every LLM result comes back from the response cache (FR-17) when the
release leaves the prompts, the rendered inputs and the output schemas unchanged — a release that changes
any of them re-pays those calls, which ADR-027's cost gate estimates. No migration code is kept in the
tool.

### Fork 4 — Claims, a brief lock, and an input check: (c)

**Three mechanisms, each guarding a different hazard:**

| Mechanism | Guards | Behaviour on conflict |
|---|---|---|
| **A claim** on each folder or file set an invocation writes (e.g. `ts-source/` and its records) | Two invocations writing the same output | **Fail fast**, naming the holder (a refusal — ADR-031) |
| **A brief lock** held only while archiving and writing the manifest | Lost updates to the manifest and the archive | **Wait** up to `lock_wait_seconds` (default 10, a setting), then fail |
| **An input check** just before publishing — the input fingerprints are re-read | An input superseded mid-run (e.g. the graph re-written while a render runs) | **Do not publish**; outputs built from superseded inputs are discarded (a refusal, safe to retry) |

**So invocations that write disjoint outputs run in parallel** — a CI matrix rendering `ts` and `go` from
one run — while overlapping writes are refused rather than interleaved (FR-44 AC-1, AC-2).

**Outputs are written under temporary names and renamed into place**, so an interrupted invocation
leaves nothing half-written indexed as complete (FR-44 AC-4).

**What a holder records.** A claim, the brief lock and the recovery journal (Fork 5) each record the
identity of the process that holds them:

- **the host**, as a one-way hash of its name — enough to compare, and no machine's name is written
  into a run directory that may be committed;
- **the process-id space** — the boot session and, where the operating system has one, the process
  namespace — because two process-id spaces can share one host name: Windows and WSL on one machine, two
  WSL distributions, two containers;
- **the process id and the process's start time**, as the operating system reports it, compared to the
  whole second — so an id the system has since given to another process is not taken for the holder;
- **the invocation's identifier** (ADR-030), so a refusal names the invocation that holds it, which
  `history` shows.

**Stale claims and locks** — a process that crashed. The stale test compares the host, the process-id
space, the process id and its start time:
- same host and process-id space, holding process no longer running, or its id now naming a process with
  another start time → taken over, with a warning;
- same host and process-id space, holding process running with the recorded start time → a genuine
  conflict, handled as above (a claim is refused, the brief lock is waited for);
- another host, or another process-id space → refused, offering `--break-lock`, which asks for consent
  under ADR-031 — the tool cannot tell whether that holder is alive.

**A restart reads as another process-id space.** The boot session is part of the recorded space, so a
claim, lock or journal left before the machine — or WSL — restarted is refused like one from another
space: from what is recorded, the two cannot be told apart. The refusal message says that `--break-lock`
is safe when the machine has restarted since the holder ran, or when the named invocation has ended in
the shell that started it.

**This is the project's one liveness rule.** ADR-030 records the same identity in each invocation's
`started` entry and applies this test to tell an interrupted invocation from a running one.

**Claims and locks live in the run directory** (ADR-029 places them), never in a relocated project.
**One machine per run directory** is documented; network file systems with weak locking are not
engineered for. **Two run directories rendering into the same `--source-out` folder at the same time**
are also documented as unsupported: claims live in each run directory, and nothing of the tool's may be
placed inside a project. One after the other is safe — the second render finds a folder with content and
no file list of its own, and is refused (Fork 2).

### Fork 5 — Roll back an unfinished invocation: (a)

**Before the first archive move, the invocation writes a journal** to `.locks/` (placed by ADR-029): its
own identity, recorded as a claim records it (Fork 4), the moves it is about to make and the outputs it
is about to publish. The journal is deleted once the manifest and the history's `finished` entry are
written.

- **A failing invocation** — a hard ceiling reached, a write error — **rolls itself back before exiting**:
  the outputs it published are removed, the outputs it archived are moved back, the journal is deleted.
- **The journal carries a format version.** A journal in a format version this release of the tool does
  not read — one written by another release — is **treated as a journal from another process-id space**
  (the bullet below): its owner and its recorded moves cannot be read, so it is never rolled back. A
  command that publishes outputs is refused, offering `--break-lock`; a command that publishes nothing
  reports the journal and its format version, leaves it in place and proceeds. The refusal message
  says what `--break-lock` leaves: it removes the journal and rolls nothing back, anything the crashed
  invocation archived stays in the archive, and `run` re-creates the run directory. The journal is
  tool-internal state, not an artefact, so ADR-035's rule for artefacts does not cover it.
- **After a crash** the journal remains. **The next invocation of any command finds it first and applies
  Fork 4's stale test to the journal's owner**, because a journal also exists for every invocation still
  publishing:
  - owner still running → the journal is left alone; it belongs to a live invocation mid-publish;
  - another host or process-id space → a command that publishes outputs is refused, offering
    `--break-lock`, as for a claim; a command that publishes nothing (`history`, `eval report`) reports
    the journal, leaves it in place and proceeds — ADR-030 shows that invocation as *cannot tell*;
  - owner stopped, with no `finished` entry in the history → **rolled back the same way**; the recovery
    is recorded in the history (ADR-030), and the invocation continues with its own work;
  - owner stopped, with a `finished` entry — a crash after step 7, before the journal was deleted → the
    journal is deleted without a roll-back: the publish completed, and the history already says so.
- The archived copy of the previous manifest makes the roll-back checkable: afterwards, the root manifest
  is byte-identical to that copy.

The previous state is restored and nothing is lost; the failed invocation's new outputs are discarded, and
a re-run reproduces them — the graph is deterministic, and LLM results are cached when the release leaves
the prompts, the rendered inputs and the output schemas unchanged (Fork 3).

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-025
Every artefact records the fingerprints of what it was built from — for a rendered project, the graph
and the annotations — so *superseded* can be decided (Fork 1); each rendered target's file list holds
every file render produced with its hash (Fork 2).

#### Constraint flagged for ADR-029
The recovery journal lives in `.locks/` (Fork 5).

#### Constraint flagged for ADR-030
The history records, per invocation, what it archived and what was purged; archive folders are named
by invocation id (Fork 1); a recovery appends an entry naming the unfinished invocation and what was
undone (Fork 5). Each `started` entry records the holder identity Fork 4 defines, so the history and the
claims judge a process by one test.

#### Constraint flagged for ADR-031
Every refusal here — a render into a folder with no file list, an earlier-version folder, a held
claim, a superseded input, a claim, lock or journal from another host or process-id space, a journal in
a format version the tool does not read — carries
ADR-031's refusal status; `purge` and
`--break-lock` follow its consent rule, including refusing without `--yes` when nothing can prompt.

### Locations

The locations a run directory and a rendered project may not occupy — the working directory, an
ancestor of it, the run directory itself, its namespaces — are placement rules, decided in **ADR-029**.

## Consequences

**Positive.**
1. Re-running is the ordinary path, with no override.
2. Nothing the user did is lost without a command that says so — overwritten and removed files go to the
   archive.
3. An earlier result stays inspectable until purged, so comparing two runs needs no planning.
4. Renders of different targets can run in parallel from one run.
5. CI gets a refusal it can retry instead of a corrupted directory, and a crash or failure is rolled back
   to a consistent one.

**Negative.**
1. The archive grows until the user purges it; its size is reported, not bounded.
2. Claims, a brief lock, an input check and a recovery journal add moving parts, and a stale-lock path,
   to build and test.
3. `--force` is removed, so scripts that use it break.
4. Folders from the earlier layout must be re-run, not migrated.
5. Using one run directory from several machines, and rendering into one `--source-out` folder from two run
   directories at once, are documented as unsupported rather than prevented.
6. The four re-render modes are more to learn than one flag.
7. The stale test reads a process's start time and its process-id space from the operating system, which
   each platform reports differently.
8. A claim, lock or journal left before a restart, or by the other shell on the same machine, waits for
   `--break-lock`: the tool cannot tell it from a live holder elsewhere, so the roll-back a crash needs is
   not automatic when a restart followed the crash.

## Confirmation

1. A second `codeograph run` into a run directory with a scorecard from the first run moves that scorecard
   to `archive/<time>-<invocation id>/evals/` and leaves an untouched copy of the previous manifest there
   (integration test).
2. A re-run that only adds outputs (a `run --ast-only` followed by a full `run`) archives only what it
   rewrites — the graph — and nothing else (integration test).
3. Every refusal in Fork 4 happens before any archive move: after a refusal, the run directory is
   byte-identical to before (integration test).
4. With the archive on another drive, each archived file's hash is verified before its original is
   removed (unit test).
5. `codeograph purge --keep 1` removes all but the newest archive folder; without `--yes` in a
   non-interactive session it refuses and removes nothing (integration test).
6. After a re-render with the default `--on-existing keep`, an edited generated file is byte-identical to
   the user's version, a user-added file is untouched, and both are reported (integration test).
7. Each of `keep-regenerate-deleted`, `overwrite-edited` and `clean` produces the outcome in its table row,
   and every overwritten or removed file is present in the archive (integration tests, one per mode).
8. A first render into a non-empty folder with no file list is refused and changes nothing; the message
   names the number of files that would be overwritten (integration test).
9. `run --force` and `render --force` are rejected as unknown options (CLI test).
10. A directory with a bare `graph.json` and no history is refused before any write, with a message
    naming the re-run command (integration test).
11. Two renders of different targets against one run, started together, both succeed and the manifest
    holds both targets' entries; two renders of the same target — the second is refused while the first
    holds its claim (concurrency test).
12. Re-writing the graph while a render runs causes the render to publish nothing (concurrency test).
13. A claim left by a killed process on the same host is taken over with a warning; one held by a live
    process is not (unit test).
14. Killing a run after the archive move and before the manifest write, then running any command,
    restores the previous manifest byte-identically and moves the archived outputs back; the history
    records the recovery (fault-injection test).
15. A run that reaches a hard ceiling after archiving rolls itself back before exiting with status 1
    (integration test).
16. `render --on-existing clean` leaves files the project's `.gitignore` covers (e.g. `node_modules/`) in
    place and reports them (integration test).
17. A cross-drive archive copy that fails part-way leaves no partial archive folder and every original
    untouched (fault-injection test).
18. A claim whose process id now names a process with another start time is taken over; a claim recorded
    from another process-id space under the same host name is refused, offering `--break-lock` and naming
    the holder's invocation identifier (unit test).
19. A `history` or `eval report` run while a `render` is publishing leaves that render's journal and
    outputs untouched (concurrency test).
20. A journal left behind after its invocation's `finished` entry is deleted without a roll-back; the
    published outputs and the manifest are unchanged (fault-injection test).
21. No claim, lock or journal contains the host's name (unit test).
22. A `history` run from another process-id space while a `render` publishes shows that render as *cannot
    tell*, leaves its journal untouched and exits 0; a `render` run from there is refused (concurrency
    test).
23. A journal recording an earlier boot session is refused by a publishing command, and the message says
    when `--break-lock` is safe (unit test).
24. A journal in a format version the tool does not read is never rolled back: a `render` is refused with
    ADR-031's refusal status, the message naming the journal and its format version, offering
    `--break-lock` and saying that it removes the journal without a roll-back, that anything archived
    stays in the archive and that `run` re-creates the run directory, and nothing moves; a `history`
    reports the journal and its format version, leaves it
    in place and exits 0 (unit test).

## Pros and Cons of the Considered Options

### Fork 1 — Replaced output

**(c) Archive, then write. ✅ Chosen.**
* Good, because nothing is lost and an earlier result stays inspectable (FR-42).
* Good, because the same directory serves re-runs and comparisons alike.
* Good, because with Fork 5's roll-back, a crash or failure returns the directory to its previous state.
* Bad, because the archive grows until the user purges it.

**(a) Overwrite in place.**
* Good, because it is the simplest and uses no extra space.
* Good, because the directory always shows one state.
* Bad, because every earlier result is lost, and a crash mid-write leaves a mix.

**(b) Delete, then write.**
* Good, because no stale file survives a re-run.
* Good, because space never grows.
* Bad, because a crash between delete and write leaves nothing, and earlier results are lost by design.

**(d) A fresh directory per invocation.**
* Good, because nothing is ever overwritten.
* Good, because concurrency questions mostly disappear.
* Bad, because every re-run needs a new name, and outputs that should accumulate (a run, then its
  render, then its evaluation) split across directories.

### Fork 2 — Re-render

**(d) Named modes, default `keep`. ✅ Chosen.**
* Good, because the default keeps the user's work, which FR-27 AC-5 requires.
* Good, because one option cannot express a contradictory combination.
* Good, because every destructive stance archives what it replaces.
* Bad, because four values are more to learn than one flag.

**(a) Overwrite everything.**
* Good, because the project always matches the generator.
* Good, because there is nothing to choose.
* Bad, because edits are lost silently.

**(b) Refuse on edits; `--force` overrides.**
* Good, because edits are never overwritten by accident.
* Good, because it is one familiar flag.
* Bad, because the override is all-or-nothing and cannot say *which* stance the user wants.

**(c) Overwrite unedited files only.**
* Good, because edits survive with no flag.
* Good, because the project mostly tracks the generator.
* Bad, because it can leave old and new files side by side that no longer fit together, with no way to ask
  for a clean result.

### Fork 3 — Earlier-version folders

**(c) Refuse; re-run. ✅ Chosen.**
* Good, because the folder is never half-understood or changed.
* Good, because a re-run is cheap — deterministic graph, and cached LLM results when the release leaves
  the LLM inputs unchanged.
* Good, because no migration code is kept.
* Bad, because the user must run a command instead of carrying on.

**(a) Migrate on read.**
* Good, because the user notices nothing.
* Good, because old folders keep working.
* Bad, because the tool rewrites a folder the user did not ask it to touch, and keeps migration code for
  every past layout.

**(b) Refuse, plus a migration command.**
* Good, because the change is explicit.
* Good, because earlier results carry over.
* Bad, because the migration command is code that serves one transition and must still be tested.

**(d) Read both layouts.**
* Good, because nothing breaks.
* Good, because no user action is needed.
* Bad, because every reader carries two layouts forever.

### Fork 4 — Concurrency

**(c) Claims, brief lock, input check. ✅ Chosen.**
* Good, because disjoint writes run in parallel.
* Good, because each hazard has its own guard, with the right behaviour — fail fast, wait, or discard.
* Good, because the brief lock makes a stale lock rare.
* Bad, because it is three mechanisms and a stale-lock path to build and test.

**(a) One lock for the whole command.**
* Good, because it is one mechanism that covers everything.
* Good, because it is easy to reason about.
* Bad, because parallel renders of different targets serialise, and a crash leaves a long-held stale lock.

**(b) Check the manifest just before writing.**
* Good, because there is no lock to go stale.
* Good, because a lost update becomes a loud error.
* Bad, because it guards only the manifest, not the outputs, and a gap remains between check and write.

**(d) Documentation only.**
* Good, because it costs nothing.
* Good, because most users run one command at a time.
* Bad, because CI matrices are a normal use, and they would corrupt silently.

### Fork 5 — Unfinished invocation

**(a) Roll back. ✅ Chosen.**
* Good, because one rule covers a crash and a failure alike.
* Good, because nothing is lost — the archive holds everything until the roll-back moves it back.
* Good, because no manual step blocks CI after a crash on the same host and process-id space.
* Bad, because a failed run's completed new outputs are discarded and must be produced again.
* Bad, because a journal from another host or process-id space — one left before a restart included —
  waits for `--break-lock` instead of being rolled back automatically.

**(b) Roll forward when possible.**
* Good, because a run that wrote everything before crashing keeps its work.
* Good, because the user re-runs less.
* Bad, because it adds a second recovery path to build and test, for a rare case.

**(c) Refuse until repaired.**
* Good, because the user sees and controls every recovery.
* Good, because no command changes the directory on another's behalf.
* Bad, because a crash becomes a blocked pipeline until someone runs a manual command.

## More Information

### Relationships

* **ADR-029** (output layout and ownership) — this ADR applies its rules to ADR-029's ownership table, and
  ADR-029 places the archive, the claims and the lock.
* **ADR-030** (invocation identity and history) — the history records what each invocation archived and
  purged; archive folders are named by invocation id.
* **ADR-031** (command outcomes and consent) — the exit status of every refusal here, and the consent rule
  for `purge` and `--break-lock`.
* **ADR-025** (manifest schema) — amended for the input fingerprints that decide *superseded*, and each
  target's file list.
* **ADR-008** (renderer interface) — unchanged; overwrite and delete handling stays in the pipeline, as it
  decided, not in renderers.
* **ADR-017** (evaluation framework) — a scorecard whose inputs changed is superseded, and archived when a
  later invocation writes in its place.

### Requirements touched

* **FR-27 AC-3, AC-4, AC-5, AC-6** — no override to re-run; deletion only by a user's removal; overwrite
  only with consent; earlier-version folders refused (Forks 1, 2, 3).
* **FR-42** — superseded output preserved; removal only by `purge`, with consent; growth reported (Fork 1).
* **FR-44** — concurrent invocations never corrupt their outputs (Fork 4).
* **FR-45 AC-2** — a refused invocation changes nothing (Forks 2, 3, 4).
* **FR-33 AC-6** — a superseded artefact is never indexed as current (Fork 1, with ADR-025).

### References

* Requirements — `docs/requirements.md` (FR-27, FR-33, FR-42, FR-44, FR-45; glossary *Superseded
  output*, *Invocation*).

### Deferred

* **Automatic retention** (e.g. keep the last N by default) — not in v1; the archive grows until purged,
  and its size is reported.
* **Multi-machine use of one run directory** — documented as unsupported.
* **Concurrent renders from two run directories into one `--source-out` folder** — documented as unsupported.

### Open questions

* None recorded at stage 1. The cluster's design review adds any it raises.

## Revision history

* **2026-11-12** — Fork 4 states what a claim, the brief lock and the journal record about their holder
  — a hash of the host name, the process-id space, the process id and its start time — and the stale test
  compares all four. Fork 5's recovery applies that test before rolling a journal back, and deletes
  without a roll-back a journal whose invocation already recorded its `finished` entry. Exposed by the
  design review of the change that gave ADR-030 its interrupted-or-running check: the claim's content and
  its liveness test were unstated, a reused process id kept a dead holder alive, Windows and WSL share a
  host name but not process ids, and a concurrent command could roll back a live invocation's journal.
* **2026-11-18** — A claim, lock or journal also records its invocation's identifier, so a refusal names
  the holder. A command that publishes nothing proceeds past a journal from another host or process-id
  space, reporting it, as ADR-030 shows such an invocation. A holder left before a restart is stated to
  read as another process-id space, with the refusal message saying when `--break-lock` is safe; Fork 5's
  pros and cons, a Negative Consequence and the constraint flagged for ADR-031 follow. Exposed by a
  verification of the 2026-11-12 change: read-only commands were blocked where ADR-030 reported, and the
  cost of recording the boot session was unstated. The stale test names the four fields it compares, as
  a fifth field is recorded beside them.
* **2026-11-19** — Fork 5: the journal carries a format version, and a journal in a version the tool does
  not read is treated as one from another process-id space — a publishing command is refused, offering
  `--break-lock`; a command that publishes nothing reports it and proceeds; Confirmation 24 added, and the
  constraint flagged for ADR-031 lists the refusal. A release that follows a crash parses a journal an
  earlier release wrote, to roll it back, and nothing said what it does with one it cannot read. Exposed by
  ADR-035's design review, which names the journal as outside its rule for artefacts and leaves its format
  to this ADR. The same day, Fork 3, Fork 5's closing line and Fork 3's Pros and Cons state the cache
  claim's condition — the release leaves the prompts, rendered inputs and output schemas unchanged — as
  ADR-035 Fork 2 does; exposed by the re-check of that review, which found the premise stated two ways.
  The second re-check of that review added what the refusal for an unreadable journal says about
  `--break-lock` (Fork 5, Confirmation 24), and Fork 2 names a render whose file list the tool does not
  read beside a first render.
* **2026-11-19** — code citations replaced by descriptions of the behaviour; the commit anchor replaced by
  the release the Context describes; no decision changed.
