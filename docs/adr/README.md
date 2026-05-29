# Architecture Decision Records

This directory holds Codeograph's locked architecture decisions, one ADR per file, following the [MADR](https://github.com/adr/madr) template.

ADR numbers reflect **architectural layer** (input → graph → rendering → LLM → quality → cross-cutting), not the order they were designed or the runtime execution sequence. If you read them in strict number order, you'll hit forward references between layers — the recommended reading order below is grouped by topic and orders concerns the way the runtime pipeline actually flows.

---

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Locked — decision committed; changes require a new ADR or formal amendment |
| 📝 | Drafted — locked-decision form lives in `work/adr-drafts/`, awaiting promotion |
| ⬜ | Designed but not yet drafted |
| ⏸️ | Deferred — v1.1 or post-v1 scope; design not started |

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
- `ADR-022 — Run manifest + structured logging` ⬜
- `ADR-023 — Secret scanning (gitleaks)` ⬜

### 8. Deferred to v1.1 / post-v1 ⏸️
- `ADR-011 — Spring → Go mapping`
- `ADR-012 — Error-handling translation`
- `ADR-016 — Cost-control CLI`
- `ADR-019 — Snapshot + negative tests`
- `ADR-020 — LLM-judge calibration`
- `ADR-021 — Determinism contract`
- `ADR-024 — Prompt-injection / output-path safety`

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
| 022 | Run manifest + structured logging | ⬜ | Cross-cutting |
| 023 | Secret scanning (gitleaks) | ⬜ | Cross-cutting |
| 024 | Prompt-injection / output-path safety | ⏸️ | Deferred (v1.1) |

---

## Conventions

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

---

## How ADR design rounds work

ADRs are designed in **Rounds** (R1–R10), grouped by what gets locked in the same design session and sequenced by which Dev Chunk consumes them. The round sequence is **not** the same as the ADR number sequence — see `work/PROJECT-TRACKER.md` for the round-to-Dev-Chunk timeline.

The round that drafted each ADR is recorded in PROJECT-TRACKER; it isn't part of the ADR itself because the design-time ordering is operational metadata, not architectural metadata. The ADR itself only carries what's needed to understand and confirm the decision.

---

## Cross-cutting references

Some ADRs introduce concepts referenced across many others:

- **Canonical-form sha256** — defined in ADR-006 amendment; consumed by ADR-007 (goldens), ADR-015 (cache key), ADR-022 (manifest integrity).
- **`--ast-only` mode** — declared in ADR-007 §"Pipeline orchestration constraint"; honored by ADR-013 §"Decision Outcome".
- **`CallContext` (purpose, prompt_id, prompt_version, prompt_content_hash, corpus_id)** — defined in ADR-013 Fork 3; consumed by ADR-015 cache key and telemetry record.
- **Banned terms list** — operational discipline documented in `CONTRIBUTING.md`; no ADR enforces it (manual review baseline, not feature scope).

---

## References

- [MADR template](https://github.com/adr/madr) — the format used by every ADR here
- [ADR GitHub Organization](https://adr.github.io/) — broader resources on the pattern
- [Michael Nygard's original ADR essay](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) — the seminal write-up
