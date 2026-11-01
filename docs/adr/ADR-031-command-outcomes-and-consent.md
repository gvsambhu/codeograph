---
status: proposed
date: 2026-10-31
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-031 — Command Outcomes and Consent

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `bd6a837` (2026-10-31). File and
line references are to that commit.

**No decision covers how a command reports its outcome, and the exit statuses that ship disagree:**

| Situation | Exit status | Evidence |
|---|---|---|
| A wrong or missing option | 2 — Click's default for a usage error | `click.UsageError` |
| `eval` cannot read its run's manifest, or an output is missing | 2 | `cli/eval.py:62,74,106` |
| An evaluation check fails | 1 | `cli/eval.py:102`; `run --eval` at `cli/main.py:370` |
| The user declines the cost-gate prompt | 1 — Click's `Abort` | `llm/confirmation_gate.py:32` |
| `cache purge` with no criterion, or without `--force` | 0, having done nothing | `cli/cache.py:50-51, 54` |

So **2 means "the command line is wrong" in one place and "the input is missing" in another**; a run that
completed but failed a quality check is indistinguishable from one that crashed; and a command that did
nothing reports success.

**Consent is asked three different ways.** The cost gate (ADR-027) prompts on a terminal and, with no
terminal, stops unless `--yes` or `--non-interactive` is given — where `--non-interactive` means *proceed
without asking* (`llm/confirmation_gate.py:26`). `cache purge` deletes only with `--force` and is
otherwise a dry run (`cli/cache.py:38`). `run --force` and `render --force` delete with no question at all
(removed by ADR-028).

**The layout cluster adds new outcomes and new irreversible commands.** ADR-028 refuses on held claims,
superseded inputs, earlier-version folders and unadoptable folders; `purge` and `--break-lock` cannot be
undone. **The requirements ask** that success, failure, completion with recorded failures and refusal be
distinct exit statuses, and that a refusal change nothing (FR-45); that irreversible removal happen only
with explicit consent, and that a non-interactive invocation never wait for consent nor proceed without
it (FR-42 AC-4, AC-5; FR-39 AC-2, AC-3).

**This ADR decides how every command reports its outcome and when it asks for consent.** It applies to
every command, not only the layout's. It is one of four coupled decisions:

| ADR | Decides |
|---|---|
| ADR-029 | Where each output lives, and which command writes it |
| ADR-028 | What a command may overwrite, delete or refuse |
| ADR-030 | How each invocation is identified, and how the history of a run directory is kept |
| **ADR-031** (this) | How every command reports its outcome and asks for consent |

## Decision Drivers

* **CI never prompts and never corrupts** — an automated caller decides from the exit status alone,
  without parsing text (FR-45 AC-1).
* **A refusal is safe to retry** — distinguishable from a failure, and it changed nothing (FR-45 AC-2).
* **Ask only when it cannot be undone** — a question is worth its cost only where a mistake is final
  (FR-42 AC-4).
* **No silent failures** — a command that did nothing never reports success.
* **One rule for every command**, including commands added later.

## Considered Options

### Fork 1 — How a command reports its outcome

* (a) Two statuses — 0 success, 1 anything else.
* **(b) A small fixed set — 0 success · 1 failed · 2 completed with recorded failures · 3 refused ·
  4 completed, a quality gate failed. ✅**
* (c) A code per error kind (the BSD `sysexits` range, 64–78).
* (d) 0 or 1, with the outcome in machine-readable output.

### Fork 2 — When a command asks for consent

* (a) Before every operation that overwrites or removes anything.
* (b) Never — explicit flags only.
* **(c) Only when the operation cannot be undone; with no one to ask, refuse unless `--yes` is given. ✅**

## Decision Outcome

### Fork 1 — A small fixed set: (b)

| Status | Meaning | Examples |
|---|---|---|
| **0** | Success | Everything requested was produced |
| **1** | Failed — no usable result, or a precondition was not met | A usage error; a source location carrying credentials; a source that cannot be fetched (FR-24 AC-4); an unreadable manifest; misconfigured settings (FR-38 AC-2); an empty corpus (FR-24 AC-5); enrichment past its failure bound (FR-35 AC-6); a hard ceiling reached; any failure after which ADR-028 rolled the directory back |
| **2** | Completed, with outputs recorded as failed | Corpus synthesis failed but the annotations were written; some classes failed to render and were skipped and recorded; the manifest records each missing output (ADR-025) |
| **3** | **Refused — nothing changed; safe to retry** | A claim held by another invocation; an input superseded mid-run; an earlier-version folder; a run directory holding unrelated content; a project folder with content and no file list; every requested scorecard skipped as stale; consent required and not given; the cost gate declined |
| **4** | Completed; a quality gate failed | An evaluation check returned *fail* |

**Precedence.** A refusal is exclusive — nothing was done. Otherwise the most severe applies:
1 over 2 over 4 over 0.

**An interrupted invocation** (Ctrl-C) exits with 130, the shell convention; its history shows it
unfinished, and ADR-028's recovery rolls it back.

**Usage errors become 1.** Click exits with 2 for a wrong option, which here means *completed with
recorded failures*; the command line maps usage errors to 1. Every path that exits with 2 for a missing
input in the snapshot does the same.

**A declined or stopped cost gate is a refusal (3), and it changes nothing.** The gate runs after Pass 0
— its estimate needs the class count — so Pass 0's output is **held back and published only once the
gate passes**. Declining then leaves the run directory as it was (FR-45 AC-2), and the retry costs a
re-parse that the deterministic graph makes cheap.

**A failing quality gate is its own status (4).** The tool did its job — the verdict is data in the
scorecard — so it is not a failure (1). But CI usually wants to stop on it, and a distinct status lets a
pipeline decide without reading the scorecard.

**The history records the same class** (ADR-030), so a status can always be traced back.

### Fork 2 — Ask only when it cannot be undone: (c)

**The rule, for every command now and later:** *can the operation be undone?*

| Operation | Undoable? | Behaviour |
|---|---|---|
| `render --on-existing clean` or `overwrite-edited` | Yes — everything replaced is archived (ADR-028) | **No question**; reports what moved |
| `purge` (run directory) | No | Asks |
| `cache purge` | No | Asks |
| `--break-lock` | No — it may damage a live invocation | Asks |
| Passing the cost gate (ADR-027) | No — the spend is real | Asks, as ADR-027 already decided |

**When asking:** on a terminal, the command prompts and **shows what it is about to do** — what would be
removed and how much. **With no terminal** (CI, a pipe), it never waits: it refuses with status 3 unless
**`--yes`** (`-y`) is given (FR-42 AC-5; FR-39 AC-3). `--yes` is the one consent flag across the tool.

**`cache purge` follows the rule.** The dry-run-by-default and `--force` are dropped: it lists what it
would remove, then asks. Its filters align with `purge`'s — `--before <date>` and `--keep <n>` — and keep
the cache's own `--model` and `--prompt-version`; with no filter, it means everything, always behind the
question. A date is ISO 8601 (`2026-10-31`, or a UTC date-time).

**`--non-interactive` keeps its ADR-027 meaning, for the cost gate only** — proceed past the gate without
asking. It never authorises an irreversible removal: a CI script that adds it to avoid a hang must not
purge by accident. Only `--yes` does that.

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-027
The gate's stop and the user's refusal exit with 3, not Click's 1; Pass 0's output is held until the gate
passes; `--non-interactive` applies to the gate only.

#### Constraint flagged for ADR-015
`cache purge` asks for consent, refuses with 3 without `--yes` when nothing can prompt, drops `--force`
and the dry-run default, and exits 1 on a usage error (0 in the snapshot); its filters align with `purge`'s.

#### Constraint flagged for ADR-017
A failing check exits with 4; a missing or unreadable manifest exits with 1, not 2; every requested
scorecard skipped as stale exits with 3.

#### Constraint flagged for ADR-028 and ADR-029
Every refusal they name exits with 3 and changes nothing.

#### Constraint flagged for ADR-030
The history's outcome field uses these classes.

## Consequences

**Positive.**
1. CI decides from the exit status alone.
2. A refusal is visibly safe to retry.
3. A failing quality check is no longer confused with a crash.
4. A command that did nothing no longer reports success.
5. One consent rule covers every command, including future ones.

**Negative.**
1. Scripts that test for 1 or 2 change meaning.
2. Click's default status for a usage error is overridden.
3. Pass 0's output is held back until the cost gate passes, so declining the gate discards a parse.
4. `cache purge` loses its dry-run default; the listing before the question replaces it.
5. Five statuses are more to document and learn than two.

## Confirmation

1. A wrong option exits with 1 on every command (CLI test across commands).
2. `eval` against a directory with no manifest exits with 1 (integration test).
3. An LLM-enabled run whose synthesis call fails, with annotations written, exits with 2 and records the
   missing output (integration test).
4. Every refusal ADR-028 names exits with 3 and leaves every artefact byte-identical (integration test per
   refusal).
5. Declining the cost gate exits with 3 and leaves no `analysis/graph.json` from that invocation; the
   history records the outcome as refused (integration test).
6. An evaluation with a failing check exits with 4; one with an output recorded as failed and a failing
   check exits with 2 (integration tests — precedence).
7. `purge` and `cache purge` on a terminal show what would be removed before asking; with no terminal
   and no `--yes` they exit with 3 and remove nothing; with `--yes` they proceed (CLI tests).
8. `render --on-existing clean` asks nothing and reports what it archived (integration test).
9. `--non-interactive` passes the cost gate but does not let `purge` or `cache purge` proceed (CLI test).
10. `cache purge --force` is rejected as an unknown option (CLI test).
11. A render in which one class's call fails and the others succeed exits with 2 (integration test).
12. Ctrl-C during a run exits with 130 (CLI test).
13. `eval run` where every requested scorecard is skipped as stale exits with 3 (integration test).
14. A source URL carrying a token exits with 1 before anything is written (integration test).

## Pros and Cons of the Considered Options

### Fork 1 — Outcome

**(b) A small fixed set. ✅ Chosen.**
* Good, because each status says what a caller should do — accept, investigate, check what failed,
  retry, or stop on quality.
* Good, because a refusal is distinguishable from a failure, which makes retries safe to automate.
* Good, because it is small enough to keep in mind.
* Bad, because it overrides Click's default for usage errors, and existing scripts change meaning.

**(a) Two statuses.**
* Good, because it is the convention every shell understands.
* Good, because there is nothing to learn.
* Bad, because it cannot meet FR-45 AC-1, and a caller cannot tell a refusal from a crash.

**(c) A code per error kind.**
* Good, because every cause has its own number.
* Good, because `sysexits` is an established range.
* Bad, because callers need a long table to act on it, and the codes describe causes, not what to do.

**(d) 0 or 1, outcome in output.**
* Good, because the exit status stays conventional.
* Good, because the output can carry any detail.
* Bad, because every caller must parse output to decide, and a crash may produce none.

### Fork 2 — Consent

**(c) Ask only when it cannot be undone. ✅ Chosen.**
* Good, because questions are kept for the cases where a mistake is final.
* Good, because CI never hangs and never proceeds silently.
* Good, because the rule classifies future operations with one question.
* Bad, because a user must trust that "undoable" really is — the archive has to work.

**(a) Before every overwriting operation.**
* Good, because the user is never surprised.
* Good, because it needs no classification.
* Bad, because frequent questions train users to answer yes without reading, and every scripted re-render
  needs a flag.

**(b) Never ask.**
* Good, because behaviour is identical on a terminal and in CI.
* Good, because nothing ever waits.
* Bad, because one mistyped command can remove what cannot be recovered.

## More Information

### Relationships

* **ADR-027** (temporary cost-safety floor) — its gate conforms: the refusal status, held Pass 0 output,
  and `--non-interactive` confined to the gate. Its TTY-aware rule is the precedent Fork 2 generalises.
* **ADR-015** (telemetry and response cache) — `cache purge` follows Fork 2.
* **ADR-017** (evaluation framework) — the failing-check and missing-manifest statuses.
* **ADR-028, ADR-029** — every refusal they name uses status 3.
* **ADR-030** — the history records these classes.

### Requirements touched

* **FR-45 AC-1, AC-2** — distinct statuses; a refusal changes nothing (Fork 1).
* **FR-42 AC-4, AC-5** — removal only with consent; a non-interactive invocation never waits or proceeds
  without it (Fork 2).
* **FR-39 AC-2, AC-3** — the cost gate's prompt and its non-interactive behaviour (Forks 1, 2).
* **FR-37 AC-2** — selective cache removal by age, model, prompt version, or entirely (Fork 2).
* **FR-24 AC-5, FR-35 AC-6, FR-38 AC-2** — the failures that exit with 1 (Fork 1).

### References

* Requirements — `docs/requirements.md` (FR-24, FR-35, FR-37, FR-38, FR-39, FR-42, FR-45).

### Deferred

* **Budget-based consent** (dollar ceilings) — ADR-016, v1.1, supersedes the cost gate.

### Open questions

* None recorded at stage 1. The cluster's design review adds any it raises.
