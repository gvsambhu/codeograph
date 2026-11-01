# Architecture Decision Records

This directory holds Codeograph's locked architecture decisions, one ADR per file, following the [MADR](https://github.com/adr/madr) template.

ADR numbers reflect **architectural layer** (input → graph → rendering → LLM → quality → cross-cutting), not the order they were designed or the runtime execution sequence. If you read them in strict number order, you'll hit forward references between layers — the recommended reading order below is grouped by topic and orders concerns the way the runtime pipeline actually flows.

---

## Status legend

| Symbol | `status:` | Meaning |
|---|---|---|
| ✅ | `accepted` | Decision committed; changes require a new ADR or a formal amendment |
| 📝 | `proposed` | File is in this directory, decision not yet accepted — open for review |
| ⬜ | — | Number **reserved**; no file yet |
| ⏸️ | — | Number reserved, deferred to v1.1 or later; design not started |

The symbol in the index below and the `status:` field in each ADR's frontmatter describe the same
state. ⬜ and ⏸️ have no file, so they have no frontmatter — the reservation row is the whole record.

---

## Recommended reading order

For someone new to the project who wants to understand the design end-to-end, read in this order — not by ADR number:

### 1. Foundation
- [`ADR-001 — Project skeleton`](ADR-001-project-skeleton.md) — repo layout, language choice, CI baseline

### 2. Input & parsing
- [`ADR-002 — Input-agnostic design`](ADR-002-input-agnostic-design.md) — module discovery, multi-module Maven, gitignore-driven exclusion
- [`ADR-003 — Parsing strategy`](ADR-003-parsing-strategy.md) — JavaParser, Lombok synthesis, annotation scope

### 3. Graph extraction (deterministic half of the pipeline)
- [`ADR-004 — Complexity model`](ADR-004-complexity-model.md) — six metrics, cited thresholds
- [`ADR-006 — Knowledge graph schema`](ADR-006-knowledge-graph-schema.md) — node/edge taxonomy, canonical-form sha256 amendment
- [`ADR-007 — Golden-graph pattern`](ADR-007-golden-graph-pattern.md) — byte-equal regression testing, multi-corpus, reproducibility envelope

### 4. LLM infrastructure (probabilistic half of the pipeline)
- [`ADR-005 — Token utilization`](ADR-005-token-utilization.md) — prompt-cache strategy, concurrency, oversized-input handling, single-Sonnet v1
- [`ADR-013 — LLM provider abstraction`](ADR-013-llm-provider-abstraction.md) — `LlmProvider` interface, middleware pattern, LangChain wrapping
- [`ADR-014 — Prompt versioning`](ADR-014-prompt-versioning.md) — Markdown prompts with frontmatter, Jinja2 custom delimiters, content-hash pinning
- [`ADR-015 — Telemetry + response cache`](ADR-015-telemetry-and-response-cache.md) — JSONL records, SQLite content-addressed cache, cross-run reporting

### 5. Rendering
- [`ADR-008 — Pluggable renderer interface`](ADR-008-pluggable-renderer-interface.md)
- [`ADR-009 — Rendering budget cap`](ADR-009-rendering-budget-cap.md)
- [`ADR-010 — Spring Boot to NestJS/TypeScript idiom mapping`](ADR-010-spring-to-typescript-nestjs-mapping.md)

### 6. Quality & testing
- [`ADR-017 — Evaluation framework`](ADR-017-evaluation-framework.md)
- [`ADR-018 — Test strategy with pytest`](ADR-018-test-strategy-with-pytest.md)

### 7. Cross-cutting
- [`ADR-022 — Run manifest and structured logging`](ADR-022-run-manifest-and-structured-logging.md) — *manifest schema forks (1/2/7) superseded by ADR-025; logging forks remain in force*
- [`ADR-025 — Manifest schema 2.0.0 (flat layout)`](ADR-025-manifest-schema-flat-layout.md) — supersedes ADR-022's manifest forks + ADR-015's `cache_stats` shape
- [`ADR-023 — Secret scanning with gitleaks`](ADR-023-secret-scanning-with-gitleaks.md)
- [`ADR-026 — Release & version management`](ADR-026-release-version-management.md) — SemVer scheme, `0.x`→`1.0.0` at the stability gate, version sourced from package metadata
- [`ADR-027 — Temporary v1 cost-safety floor`](ADR-027-temporary-cost-safety-floor.md) — pre-flight estimate + confirmation gate + optional hard call/token ceiling; *temporary, superseded by ADR-016 at `1.1.0`*
- [`ADR-029 — Output layout and ownership`](ADR-029-output-layout-and-ownership.md) — *proposed* — where each output lives and which command writes it; on acceptance, supersedes ADR-022 Fork 5
- [`ADR-028 — What a command may overwrite, delete or refuse`](ADR-028-overwrite-delete-and-refuse.md) — *proposed* — archive, re-render modes, earlier-version folders, concurrency
- [`ADR-030 — Invocation identity and history`](ADR-030-invocation-identity-and-history.md) — *proposed* — per-invocation identifier, `runs.jsonl`, per-invocation logs
- [`ADR-031 — Command outcomes and consent`](ADR-031-command-outcomes-and-consent.md) — *proposed* — exit statuses and when a command asks

### 8. Deferred to v1.1 / post-v1 ⏸️
- `ADR-011 — Spring → Go mapping`
- `ADR-012 — Error-handling translation`
- `ADR-016 — Cost-control CLI`
- `ADR-019 — Snapshot + negative tests`
- `ADR-020 — LLM-judge calibration`
- `ADR-021 — Determinism contract`
- `ADR-024 — Prompt-injection defence`

---

## Index by ADR number (reference table)

| # | Title | Status | Reading-order group |
|---|---|---|---|
| 001 | Project skeleton | ✅ | Foundation |
| 002 | Input-agnostic design | ✅ | Input & parsing |
| 003 | Parsing strategy | ✅ | Input & parsing |
| 004 | Complexity model | ✅ | Graph extraction |
| 005 | Token utilization | ✅ | LLM infrastructure |
| 006 | Knowledge graph schema | ✅ | Graph extraction |
| 007 | Golden-graph pattern | ✅ | Graph extraction |
| 008 | Pluggable renderer interface | ✅ | Rendering |
| 009 | Rendering budget cap | ✅ | Rendering |
| 010 | Spring Boot → NestJS/TypeScript idiom mapping | ✅ | Rendering |
| 011 | Spring → Go mapping | ⏸️ | Deferred (v1.1) |
| 012 | Error-handling translation | ⏸️ | Deferred (v1.1) |
| 013 | LLM provider abstraction | ✅ | LLM infrastructure |
| 014 | Prompt versioning | ✅ | LLM infrastructure |
| 015 | Telemetry + response cache | ✅ | LLM infrastructure |
| 016 | Cost-control CLI | ⏸️ | Deferred (v1.1) |
| 017 | Evaluation framework | ✅ | Quality & testing |
| 018 | Test strategy with pytest | ✅ | Quality & testing |
| 019 | Snapshot + negative tests | ⏸️ | Deferred (v1.1) |
| 020 | LLM-judge calibration | ⏸️ | Deferred (v1.1) |
| 021 | Determinism contract | ⏸️ | Deferred (v1.1) |
| 022 | Run manifest and structured logging | ✅ (manifest forks superseded by 025) | Cross-cutting |
| 023 | Secret scanning with gitleaks | ✅ | Cross-cutting |
| 024 | Prompt-injection defence | ⏸️ | Deferred (v1.1) |
| 025 | Manifest schema 2.0.0 (flat layout) | ✅ | Cross-cutting |
| 026 | Release & version management | ✅ | Cross-cutting |
| 027 | Temporary v1 cost-safety floor | ✅ | Cross-cutting |
| 028 | What a command may overwrite, delete or refuse | 📝 | Cross-cutting |
| 029 | Output layout and ownership | 📝 | Cross-cutting |
| 030 | Invocation identity and history | 📝 | Cross-cutting |
| 031 | Command outcomes and consent | 📝 | Cross-cutting |
| 032 | Evaluation check semantics | ⬜ | Quality & testing |
| 033 | Extraction environment and parser failures | ⬜ | Input & parsing |
| 034 | Placeholders for unrendered classes | ⬜ | Rendering |

---

## Proposing a new ADR

Three steps. Step 1 is a precondition — a PR that adds an ADR file without a reserved number will be
declined.

### 1. Reserve the number

Open a PR that adds a single row to the **Index by ADR number** table above: the next free number,
the title, `⬜`, and your GitHub handle as owner. Nothing else — no ADR file yet.

The index is one file with one row per number, so two people claiming the same number produce a
merge conflict. That is the mechanism: reservation is serialised by merge, not by convention.

A reservation with no PR activity for six months may be released and the number reassigned.

### 2. Write the ADR

Once the reservation is merged, add `ADR-<NNN>-<slug>.md` to this directory with
`status: proposed`, on a branch, via PR. Use the number you reserved. Follow the template and
conventions below; an ADR that doesn't meet them will be sent back rather than declined.

Discussion happens in the PR. If the problem needs exploring before a decision is defensible, open
an issue first — that's the cheaper place for option debates than a PR thread.

### 3. Acceptance

Merge to `main` with `status: accepted`. A reviewer checks that the decision is genuinely
architectural (see "When to write a new ADR"), that at least two options were considered with real
tradeoffs, that the Confirmation section states how the decision can be verified in code, and that
no forward reference contradicts a locked ADR.

### Areas that do not accept outside proposals

These are maintainer-owned by design. Issues and discussion are welcome; ADR PRs will be declined.

| Area | Why |
|---|---|
| ADR-003 — parsing strategy | Tool-selection call reserved to the maintainer |
| ADR-004 — complexity model | Every threshold must cite a published source |
| ADR-011 — Spring → Go idiom mapping | The mapping design is the project's core exercise |
| README "Point of view" section | Author's personal voice |

---

## Conventions

### Numbering

- Three digits, sequential from `001`. **Never reuse a number**, including for a withdrawn proposal.
- Numbers `001`–`021` were allocated by architectural layer (input → graph → rendering → LLM →
  quality → cross-cutting). That scheme is closed: from `022` onward numbers are allocated in
  reservation order. The recommended reading order above carries the layer grouping instead.
- One decision per file. If a file covers two decisions, split it into two numbers.

### Status lifecycle

```
reserved (index row only) → proposed (file, status: proposed) → accepted
                                                              ↘ withdrawn (number retired, not reused)
accepted → deprecated
        → superseded by ADR-NNN
```

**A proposed ADR may be merged and implemented against.** It stays `proposed` while the code that
implements it is built and reviewed, and is **accepted only once that code has passed its development
review and reconciliation** — so a design problem the implementation exposes is fixed while the decision
is still open, not by a later amendment or supersession. Until then, a design change is edited into the
ADR directly and listed, with its date and reason, in a `## Revision history` section at the end.
Accepting it is its own change: the `status:` field moves to `accepted`. **The amendments it needs in
accepted ADRs are written when it is accepted, not before** — an accepted ADR's amendments are
immutable, so they wait until the proposal is final; meanwhile each one is listed in the proposed ADR's
*Constraint flagged* subsections.

An accepted ADR is immutable, with exactly two exceptions: its `status:` field, and append-only
`## Amendments` sections. Never edit the original decision text to reflect a later change — that
destroys the record of what was decided when, which is the entire point of an ADR. Its revision history,
if it has one, stays as the record of how the proposal evolved.

### When to write a new ADR

Write a new ADR when:
- A decision has lasting architectural consequences (call shape, data model, dependency, deployment topology)
- Reasonable people could disagree on the answer; the rationale needs to be recorded
- The decision constrains future ADRs

Do **not** write an ADR for:
- Routine library version bumps
- Coding-style choices (those live in `CONTRIBUTING.md`)
- Tactical refactors that don't change the architecture

### When to amend vs supersede

| Situation | Action |
|---|---|
| Small additive clarification (a new field, a new option) | **Amend** the existing ADR; add an "Amendment" section dated and signed |
| Material change to the decision (different option chosen, scope expanded) | **Supersede** with a new ADR; mark the old one `status: superseded by ADR-NNN` and add a link |
| Decision proved wrong in practice | **Supersede** + write a "Lessons" section in the new ADR explaining what didn't work |

### File naming

```
ADR-NNN-kebab-case-slug.md
```

`NNN` is the three-digit ADR number (`001`–`024`). The slug is a short kebab-case identifier — keep it under ~40 characters.

### Template

Each ADR follows MADR with these sections:
1. **YAML frontmatter** — `status`, `date`, `deciders`, `consulted`, `informed`
2. **Context and Problem Statement**
3. **Decision Drivers**
4. **Considered Options** — fork list with ✅ on the chosen option
5. **Decision Outcome** — per-fork detail with code samples / tables
6. **Consequences** — Positive / Negative
7. **Confirmation** — checklist of how to verify the decision is implemented correctly
8. **Pros and Cons of the Considered Options** — per-fork tradeoff breakdown
9. **More Information** — relationships to other ADRs, deferred items, references
10. **Revision history** — only for a merged ADR changed while `proposed`: one dated line per change
11. **Amendments** — only after acceptance, append-only

---

## Why the numbers don't match the design order

ADRs 001–021 were designed in batches, grouped by which decisions had to lock together, and
numbered by architectural layer rather than by the order they were written. So the number sequence
is neither the design sequence nor the runtime sequence — which is why the reading order above is
grouped by topic instead.

The design-time ordering is operational metadata, not architectural metadata, so it isn't recorded
in the ADRs themselves. Each ADR carries only what's needed to understand and confirm its decision.

---

## Cross-cutting references

Some ADRs introduce concepts referenced across many others:

- **Canonical-form sha256** — defined in ADR-006 amendment; consumed by ADR-007 (goldens), ADR-015 (cache key), ADR-022 (manifest integrity).
- **`--ast-only` mode** — declared in ADR-007 §"Pipeline orchestration constraint"; honored by ADR-013 §"Decision Outcome".
- **`CallContext` (purpose, prompt_id, prompt_version, prompt_content_hash, corpus_id)** — defined in ADR-013 Fork 3; consumed by ADR-015 cache key and telemetry record.
- **Banned terms** — a maintainer-side review discipline, not a repo-enforced rule and not owned by any ADR.

---

## References

- [MADR template](https://github.com/adr/madr) — the format used by every ADR here
- [ADR GitHub Organization](https://adr.github.io/) — broader resources on the pattern
- [Michael Nygard's original ADR essay](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) — the seminal write-up
