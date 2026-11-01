---
status: accepted
date: 2026-06-29
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-027 — Temporary v1 Cost-Safety Floor

## Context and Problem Statement

Codeograph's v1 has **no spend ceiling of any kind.** The cost-control mechanisms that exist all
bound *shape* or *failures* — never dollars or call count:

| Mechanism | Bounds | Spend cap? |
|---|---|---|
| `max_tokens=4096` per call | output tokens / call | No |
| `render_budget` / `--max-classes-per-domain` (ADR-009) | classes *rendered* (Pass 3) | Partial |
| oversized → `signatures_only` (ADR-005) | input tokens / oversized class | No |
| prefix caching | re-billed input (~90 % off on hit) | No (reduction only) |
| `max_pass1_failure_ratio` + min-3 floor | aborts on **failures** | No (failure guard) |
| `llm_concurrency=5` | parallel calls | No |

The exposure this ADR closes is **Pass-1 annotation, which is unbounded** — N calls for N classes,
with no cap, warn, or kill. An 8,000-class monolith on the v1 default (`claude-sonnet-4-6`) issues
8,000 calls and nothing stops it. There is also no live spend tally for anything to react to:
`cost_usd_est` is hardcoded to `0.0` in the telemetry provider, so the field exists but is never
computed.

Full dollar-accurate budgeting (`--max-cost-usd`, `--budget-warn`, live spend) is already planned
for **ADR-016 / v1.1** and depends on a live cost tally that v1 does not have. But v1 ships to users
**now**, and a first-run user must not be able to accidentally launch an unbounded paid fan-out.
This ADR introduces a deliberately-minimal, **temporary** cost-safety floor to cover the gap between
v1 shipping and ADR-016 landing. **ADR-016 supersedes this floor at `1.1.0`** (an additive MINOR bump
per ADR-026).

The scope is narrow and explicit: a pre-flight estimate shown before any LLM run, a confirmation gate
above a default threshold, and an optional hard ceiling that aborts mid-run. It is **not** budgeting,
**not** live cost tracking, and **not** per-stage cost policy — those are ADR-016 / v1.1.

## Decision Drivers

* **No accidental unbounded spend on a first run.** The floor must protect a user who did not read
  the docs; a pure opt-in cap protects nobody.
* **Never hang a pipeline; never silently spend in CI.** Eval and golden runs (ADR-007 / ADR-017)
  execute non-interactively; a `[y/N]` prompt cannot block them, and a silent uncapped run cannot be
  allowed either.
* **Honest numbers.** The pre-flight dollar figure is an estimate from a dated static table, not a
  quote, and must be labelled as such.
* **Model-agnostic floor with an optional precision layer.** Call count is meaningful for every
  provider; a token ceiling adds precision where a running tally already exists (ADR-013 `TokenUsage`).
* **Temporary by construction.** The floor accrues no permanent interface debt — it is removed when
  ADR-016 lands. It must not entangle with the future permanent budget surface.
* **Citation discipline (ADR-004).** Any default threshold cites its rationale rather than inventing
  an external source.

## Considered Options

Each fork was evaluated against the drivers; the ✅ option is the locked decision. Rejected-option
detail is in the Pros and Cons section.

### Fork 1 — What does the hard ceiling abort on?

* (a) Call count only.
* (b) Total tokens only.
* **(c) Both — `--max-llm-calls` primary + optional `--max-tokens-total`. ✅**

### Fork 2 — Default-on or opt-in?

* (a) Pure opt-in cap (flag-only; off by default).
* **(b) Safety-by-default — estimate always shown; confirmation required above a default threshold;
  hard cap opt-in via flag. ✅**

### Fork 3 — Non-interactive / CI behaviour

* (a) Always prompt.
* (b) Never prompt; rely on the hard cap only.
* **(c) TTY-aware — prompt on a TTY; in a non-TTY auto-abort unless `--yes` / `--non-interactive`. ✅**

### Fork 4 — Estimate provenance / honesty

* (a) Show a dollar figure with no provenance note.
* (b) Show call/token count only, no dollar figure.
* **(c) Dollar figure from a dated static price table, explicitly labelled "estimate, not a quote". ✅**

## Decision Outcome

### Fork 1 — (c): hard ceiling aborts on calls (primary) + tokens (optional)

The hard ceiling exposes two flags:

* `--max-llm-calls N` (primary) — a model-agnostic floor every provider honours; the run aborts when
  the Nth LLM call would be exceeded.
* `--max-tokens-total M` (optional precision layer) — rides the existing `TokenUsage` tally
  (ADR-013 Fork 5); the run aborts when cumulative input+output tokens would exceed M.

Whichever bound is reached first aborts the run with a clear message naming the bound that tripped and
the partial-progress state (how many classes were annotated before the abort). Neither flag is set by
default — the hard cap is opt-in (Fork 2); when unset, the safety behaviour is the pre-flight estimate
plus the confirmation gate.

### Fork 2 — (b): safety-by-default, three layers

1. **Pre-flight estimate — always shown.** Before any LLM call, Codeograph prints the estimated call
   count and approximate cost (Fork 4) for the run.
2. **Confirmation gate — required above a default threshold.** When the estimated call count exceeds
   the default threshold, the run requires confirmation to proceed (subject to Fork 3's TTY rule).
3. **Hard cap — opt-in.** `--max-llm-calls` / `--max-tokens-total` (Fork 1) are off unless set.

**Default confirmation threshold = 100 LLM calls** (configurable; proposed CLI/Settings name
`llm_call_confirm_threshold`). *Rationale (ADR-004 discipline):* the dated cost table
(`docs/model-selection-and-cost.md` §7) puts a ~300-class service at ~\$3–5 on the v1 default
`claude-sonnet-4-6`; Pass-1 issues ≈ one call per class plus one Pass-2 synthesis, so call count ≈
class count. ~100 calls is therefore ≈ \$1–1.7 on the default model — the point where a casual
first run begins to incur non-trivial spend, while smaller runs (e.g. a ~25-class sample service)
stay in the cents and never prompt. This is an **explicitly-accepted operational heuristic** tied to
the dated cost table — not an external citation — in the same spirit as ADR-005 D-005-4's 80K cap.
It is user-overridable.

### Fork 3 — (c): TTY-aware non-interactive behaviour

* **On a TTY:** show the estimate; if the threshold is exceeded, prompt `Proceed? [y/N]` and abort on
  anything other than an affirmative.
* **In a non-TTY** (CI, pipes, eval/golden runs): if the threshold is exceeded, **auto-abort** with a
  clear message **unless** `--yes` (`-y`) or `--non-interactive` is passed, in which case the run
  proceeds without prompting. Eval/golden CI either passes the explicit flag or runs `--ast-only`
  (which instantiates no provider per ADR-013 and is unaffected). This never hangs a pipeline and
  never silently spends.

### Fork 4 — (c): labelled, dated estimate from a machine-readable source

The pre-flight dollar figure is computed from a **dated, machine-readable price source** — the single
source of truth for prices — and rendered with an explicit caption: *"estimate from a dated price
table, not a quote — actual cost depends on model, caching, and provider pricing; verify before
relying."* The human-readable table in `docs/model-selection-and-cost.md` (§6) is kept in sync with
that source and carries the same caveat; **the estimator reads the structured source, never parses
the prose table.** The price-source file format is the learner's tech choice (e.g. `prices.toml`);
a CI parity check (doc table vs structured source) is recommended — the same regenerate/compare
pattern as the ADR-014 prompt-freshness and ADR-023 pin-parity gates — though for a temporary feature
a lightweight check suffices. (External price *accuracy* cannot be CI-gated — that is inherently
manual; only doc-vs-source *parity* can.)

Three robustness rules make the honesty claim hold as prices move:

* **Staleness signal.** The estimate prints the price-source date; if it is older than a staleness
  window (default 90 days ≈ one refresh cycle, configurable), it appends a "price data is N days old
  — verify" warning. Drift is usually downward (models get cheaper), so a stale source tends to
  *over*-estimate — the safe direction for a guard — but the signal makes staleness visible rather
  than silent.
* **Unknown-model degradation.** If the selected model has no row in the price source (the provider
  abstraction allows free-form model ids), the estimate shows the **call/token counts only** and
  states "no price data for `<model>` — cost estimate unavailable." It never shows `$0` and never
  fails the run; the call-count safety floor (Forks 1–2) is unaffected because it does not depend on
  prices.
* **Telemetry.** `cost_usd_est` (today hardcoded `0.0`) MAY be populated from the same source and is
  likewise marked indicative; live-billing accuracy is ADR-016.

**The static price source is a known, deliberate limitation, not the long-term answer.** Accurate
cost requires live per-call billing — that is ADR-016 / v1.1, the ADR that supersedes this floor at
`1.1.0`. The call-count bound (Fork 1) is price-independent precisely so the *protection* never
depends on the *table*; only the advisory dollar figure does.

### Implementation shape (design fixed here; code is implemented in a later dev chunk)

* **Pre-flight count derivation.** The estimate is derived **after parsing / class discovery and
  before any LLM call** — Pass-1 call count = number of annotatable classes, plus one Pass-2 call.
  No LLM call is needed to produce the estimate.
* **Hard-ceiling placement.** The call/token ceiling is enforced by a counting middleware wrapper that
  composes in the existing `LlmProvider` stack (ADR-013 Fork 3, `Telemetry → Caching → Retry →
  Provider`); it is added to the stack when either cap flag is set. The pre-flight estimate +
  confirmation gate run **once before the fan-out**, not per call.
* **CLI flags** (proposed; confirm against ADR-001 CLI conventions): `--max-llm-calls`,
  `--max-tokens-total`, `--yes`/`-y`, `--non-interactive`.

This ADR fixes the design; the estimator, the confirmation gate, the counting wrapper, and the flag
wiring are built in a later dev chunk per the project DoD.

### Removal contract

The entire surface is **superseded by ADR-016 at `1.1.0`**. When ADR-016's dollar-accurate budgeting
(`--max-cost-usd`, live spend) lands, the ADR-027 flags and confirmation gate are removed or folded
into ADR-016's permanent surface. ADR-026 defines no "temporary-feature / remove-at-version"
convention, so ADR-027 stands alone with a plain supersession pointer.

## Consequences

**Positive.**

* Closes the unbounded-Pass-1 bill-risk for v1 without waiting for ADR-016.
* Safety-by-default protects users who didn't read the docs; the threshold keeps small runs
  friction-free.
* TTY-aware behaviour keeps eval/golden CI green and never hangs a pipeline.
* The honest, dated estimate avoids implying a precise quote the tool can't back.
* Temporary by construction — removed cleanly at `1.1.0`; no permanent interface debt.
* Reuses existing seams (ADR-013 middleware stack + `TokenUsage` tally; the cost-doc price table),
  so the added surface is small.

**Negative.**

* A second, throwaway cost surface exists for one minor version. Deliberate; the removal contract is
  documented.
* **The static price source drifts** as vendor prices move (typically downward, ~monthly). This is a
  known, deliberate limitation of a temporary feature — accurate cost is ADR-016's live billing
  (v1.1). Mitigated meanwhile by: the call-count bound being price-independent (protection never
  drifts); the staleness signal; unknown-model degradation; and the dated "estimate, not a quote"
  label.
* The default confirmation threshold is a judgement call. Mitigated by tying it to a cost-table row
  and making it configurable.
* Deriving the pre-flight call count requires the class count before Pass 1 — one extra discovery
  read (already available from parsing).

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. A run whose estimated call count exceeds the default threshold **prompts on a TTY** and
   **auto-aborts in a non-TTY** when neither `--yes` nor `--non-interactive` is passed.
2. The same run **proceeds without prompting** in a non-TTY when `--yes` / `--non-interactive` is
   passed.
3. `--max-llm-calls N` aborts the run after N calls; `--max-tokens-total M` aborts after M tokens;
   whichever bound trips first wins, and the abort message names the bound and the partial progress.
4. The pre-flight output **always** shows the estimated call count and the approximate cost, with the
   dollar figure labelled an estimate and carrying the price-table date.
5. An `--ast-only` run (no provider instantiated, per ADR-013) shows **no** estimate and **no** gate.
6. The default confirmation threshold value is documented with its cost-table rationale (ADR-004
   discipline) and is overridable via CLI/Settings.
7. The pre-flight output prints the price-source date and warns when it is older than the staleness
   window.
8. A model with no price row yields a **count-only** estimate ("no price data for `<model>`") — not
   `$0` and not a failure — and the run's call-count safety floor still applies.
9. The estimator reads the **structured price source**, not the prose markdown table; the doc table
   and the source are kept in sync (parity check recommended, ADR-014 / ADR-023 pattern).

## Pros and Cons of the Considered Options

### Fork 1 — Hard-ceiling bound

**(a) Call count only.** Good: model-agnostic, trivial to count. Bad: coarse — a few huge calls slip
under a call cap.
**(b) Total tokens only.** Good: precise cost proxy. Bad: provider-specific tokenization; no simple
floor; harder to explain to a first-run user.
**(c) Both — calls primary + optional tokens. ✅ Chosen.** Good: calls give an explainable floor,
tokens add precision on the existing tally; either bound aborts. Bad: two flags to document.

### Fork 2 — Default-on vs opt-in

**(a) Pure opt-in.** Good: zero friction; no behaviour change. Bad: protects nobody who didn't read
the docs — defeats the purpose.
**(b) Safety-by-default. ✅ Chosen.** Good: estimate always shown; confirmation only above a
threshold; hard cap stays opt-in. Bad: adds a prompt to the default path (mitigated by the threshold
and `--yes`).

### Fork 3 — Non-interactive behaviour

**(a) Always prompt.** Good: simplest rule. Bad: hangs CI — a non-TTY can't answer `[y/N]`.
**(b) Never prompt; cap only.** Good: never hangs. Bad: silent spend up to the cap; no confirmation
for an interactive user who would want one.
**(c) TTY-aware. ✅ Chosen.** Good: prompts a human, auto-aborts a pipeline unless explicitly waived;
never hangs, never silently spends. Bad: TTY detection is one more branch to test.

### Fork 4 — Estimate provenance

**(a) Unlabelled dollar figure.** Good: looks precise. Bad: dishonest — implies a quote it can't
back.
**(b) Counts only, no dollars.** Good: no accuracy claim to defend. Bad: drops the number users most
want.
**(c) Dated, labelled estimate from the cost-doc table. ✅ Chosen.** Good: honest, sourced, and ties
the doc-only cost work to a shipped feature. Bad: the table needs date-stamping and periodic refresh
discipline.

## More Information

**Relationships to other ADRs.**

* **Superseded by ADR-016 (target removal: `1.1.0`).** ADR-016 (cost-control CLI, v1.1) ships
  dollar-accurate budgeting (`--max-cost-usd`, `--budget-warn`, live spend); at `1.1.0` it supersedes
  this temporary floor. `1.1.0` is an additive MINOR bump per **ADR-026**.
* **Narrows ADR-005 D-005-3.** D-005-3 states v1 has "no estimate, no cap — prefix caching only."
  ADR-027 narrows that to a temporary pre-flight estimate + hard call/token ceiling. A reciprocal
  narrowing pointer lands in ADR-005's Amendments section with the related provider-expansion
  amendment package. Full dollar-accurate budgeting remains ADR-016 / v1.1.
* **Shares the cost-doc price table.** The pre-flight dollar figure consumes the same dated static
  price table as `docs/model-selection-and-cost.md` (Fork 4). Both carry the "estimate, not a quote;
  verify before relying" caveat.
* **ADR-013** supplies the implementation seam — the counting/ceiling middleware composes with the
  existing `Telemetry → Caching → Retry → Provider` stack (Fork 3); `--max-tokens-total` rides the
  `TokenUsage` tally (Fork 5).
* **ADR-007 / ADR-017** (golden + eval, CI) drive Fork 3 — those runs are non-interactive and either
  pass `--yes` / `--non-interactive` or use `--ast-only`.
* **ADR-026** defines the `1.0.0` / `1.1.0` lines the supersession timing is expressed against.

**Deferred items (explicitly NOT this ADR).**

* Dollar-accurate budgeting, `--max-cost-usd`, `--budget-warn`, live spend tracking → ADR-016 / v1.1.
* Populating `cost_usd_est` from live billing (vs the static table) → ADR-016 / v1.1.
* Per-stage (`fast` / `deep` / `render`) cost policy → out of scope.

**Open questions for future review.**

1. Did the default threshold (100 calls) prove right in practice, or did real first-runs want it
   higher/lower?
2. Did the counting middleware stay a clean wrapper, or did ceiling logic leak into the orchestrator?
3. When ADR-016 lands, is the ADR-027 surface removed cleanly, or did anything come to depend on it?

**References.**

* MADR template — https://github.com/adr/madr
* `docs/model-selection-and-cost.md` — shared dated price table (Fork 4 data source)
* ADR-016 (cost-control CLI, v1.1) — the permanent budget surface that supersedes this floor
* ADR-005 §3 / D-005-3 — the "no cost cap in v1" line this ADR narrows
* ADR-013 Forks 3 & 5 — middleware composition seam + `TokenUsage` tally
* ADR-026 — SemVer / `1.0.0`→`1.1.0` lines

## Amendments

**2026-06-29 — endpoint-aware price keying (1 decision).** Surfaced by the design review of the
ADR-013 D-013-7 / ADR-001 D-001-5 provider expansion (reviewed jointly per guideline 06 §0.1). Fork 4
assumed model id alone identifies a price — true when the v1 provider set was Anthropic + OpenRouter,
but the generic OpenAI-compatible provider (D-013-7) makes the **same model id reachable on different
hosts at different prices, or free**. Fork 4's pricing is amended to match; the locked decision
(temporary, labelled, dated estimate; call-count floor is price-independent) is unchanged.

1. **Price source keyed by `(provider label, model)`, not model id alone.** The price lookup uses the
   endpoint **provider label** that ADR-013 D-013-7 / ADR-001 D-001-5 record (explicit
   `CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL`, else the normalized base-URL host) — the same label used
   in the cache key and telemetry. The cost doc's price table (`docs/model-selection-and-cost.md` §6)
   carries a provider/endpoint column so one model id can hold different prices per host.
2. **Unknown-model degradation re-stated per pair.** Fork 4's rule "if the selected *model* has no row
   → count-only estimate, *no price data for `<model>`*" now reads "if the selected **`(label, model)`
   pair** has no row → count-only estimate, *no price data for `<model>` on `<label>`*."
3. **Free/local routes resolve to `$0`.** A `(label, model)` the price source marks free or local
   estimates `$0`, not "unknown" and not a stale paid figure.

**New Confirmation items (from this amendment):**
* The pre-flight estimate looks up price by `(provider label, model)`; the same model id on two hosts
  can yield two different estimates.
* A `(label, model)` pair absent from the price source yields a count-only estimate
  ("no price data for `<model>` on `<label>`"), not `$0` and not a failure.
* A route the price source marks free/local estimates `$0`.

No locked decision reversed; Fork 4's pricing is aligned to the provider expansion (the protection
remains price-independent — only the advisory figure gains endpoint awareness). Clarification +
additive only.
