---
status: "accepted"
date: 2026-04-21
decision-makers: Ganesh
consulted: —
informed: —
---

# ADR-005 — Token Utilization Strategy

## Context and Problem Statement

Stage 3 of the pipeline is the LLM extraction layer. Per ADR-003, the LLM is invoked in a two-pass pattern:
* **Pass 1** — N calls (one per class) for semantic extraction (domain label, NL summary, migration hazards, optional quality observations).
* **Pass 2** — one call for cross-domain synthesis (input = aggregated Pass 1 outputs).

Pass 1 is the cost driver. Pass 1 scales linearly with class count N. Realistic Codeograph inputs span ~10² (a single Spring Boot microservice — e.g., Spring PetClinic at ~25 classes, a typical bounded-context service at 200–800) to ~10⁴ (large modular monoliths in the 3,000–8,000 class range), with typical enterprise services landing in the 300–1,500 class band. At any N in that range, naïve invocation has compounding waste: identical system / schema / idiom prefixes re-billed every call, oversized classes degrading attention quality, and unbounded concurrency tripping rate limits.

This ADR pins the *mechanics* of how Codeograph uses LLM tokens — separate from what prompts go through them (ADR-014) and which provider runs them (ADR-013). Five mechanical decisions are made here: prompt-cache strategy, sync vs batch API, oversized-input handling, model selection per pipeline stage, and concurrency / retry policy. A sixth (orchestration framework choice) is a constraint flagged by this ADR for ADR-013 to honour.

## Decision Drivers

* **Cost ceiling on Pass 1.** Identical prefix tokens across N calls must not be re-billed N times.
* **Quality consistency across the graph.** Oversized inputs must not degrade extraction quality silently.
* **Single-model determinism for v1.** v1 prefers uniform output style across the graph for clean eval comparison.
* **Tractable v1 implementation.** Avoid features that require dropping below LangChain into raw SDK plumbing for v1 (batch API, mid-run model switching).
* **Forward compatibility.** v1.1 will gain batch, multi-model tiering, and cost-control CLI flags (ADR-016) — v1's design must not block these.

## Considered Options

**Caching strategy**
* C1 — single cache breakpoint at end of (system + schema + target-language idiom reference); per-class content as variable suffix; 5-min TTL  *(chosen)*
* C2 — two breakpoints (after system, after idiom reference) for multi-target-language runs
* C3 — no caching in v1

**Sync vs Batch**
* B1 — sync only in v1; batch deferred to v1.1  *(chosen)*
* B2 — sync default + `--batch` opt-in flag in v1
* B3 — auto-batch when class count > threshold

**Oversized-input handling**
* O1 — send whole class always
* O2 — chunk oversized methods, merge results
* O3 — signatures-only fallback when over a token cap
* O4 — escalate oversized to a higher-tier model
* **O1 default + O3 escape hatch** — send whole class normally; fall back to O3 only when class exceeds a hard token cap  *(chosen)*

**Model selection**
* M1 — single model (Sonnet) for all stages  *(chosen for v1)*
* M2 — tiered: Haiku for Pass 1, Sonnet for Pass 2
* M3 — configurable per stage via settings  *(chosen for v1.1)*

**Concurrency**
* Default 5 concurrent in-flight calls; configurable via `Settings`  *(chosen)*

**Orchestration framework (constraint flagged for ADR-013)**
* LangChain with native prompt-cache pass-through to provider  *(chosen)*

## Decision Outcome

### 1. Caching — C1: single breakpoint, 5-min TTL

Pass 1 prompts are structured as:

```
[ system prompt + schema instructions + target-language idiom reference ]   ← cache breakpoint here
[ per-class facts + class source body ]                                     ← variable suffix
```

The prefix is marked `cache_control={"type": "ephemeral"}` (Anthropic terminology — `ChatAnthropic` propagates this through LangChain). TTL = 5 minutes (default; sufficient for a typical run).

* The single target language is fixed for the whole run (per CLI invocation), so the idiom reference belongs in the cached prefix.
* Cache write cost (1.25× input) breaks even after ~3 hits; any non-trivial project clears this immediately.
* No multi-target-language run pattern is supported in v1, so C2's second breakpoint earns nothing.

Pass 2 (cross-domain synthesis) is a single call — caching has no value there. No breakpoint applied.

### 2. Sync vs Batch — B1: sync only in v1

* All LLM calls in v1 are issued via the sync (Messages) API.
* Pass 1's N calls run concurrently (Fork 5 below) but each is an independent sync request.
* **Batch API (50% discount, up to 24h latency) is deferred to v1.1.** Implementation cost in v1.1 is ~1–2 dev days plus a contained architectural seam: LangChain's `ChatAnthropic` does not wrap the Batch API endpoint, so v1.1's batch path will call the Anthropic SDK directly for batch submission/polling and feed results back into the LangChain structured-output flow.

### 3. Oversized input — O1 default + O3 escape hatch

Per ADR-003, the per-class LLM call sends class facts + the class source. The natural "oversized" unit is the **class**, not any individual method.

**Default behaviour (O1):**
* The full class source is sent in one prompt.
* Sonnet's 200K context window covers the overwhelming majority of real Spring Boot classes (typical class < 1000 LoC ≈ < 5K tokens).

**Escape hatch (O3):** when an estimated token count for a class exceeds a configurable cap:
* Default cap: **80,000 tokens** (well below Sonnet's 200K limit; chosen as a quality-degradation threshold, not a context-fit threshold).
* Token estimate uses a conservative ratio (~3 chars per token for Java source).
* Signatures-only mode: only class declaration, field declarations, and method signatures are sent to the LLM. Method bodies are dropped from the prompt.
* The resulting class node is tagged `extraction_mode: signatures_only` in the graph (alongside the existing `ast` and `regex_fallback` modes from ADR-003).
* The class is recorded in the run manifest (ADR-022) with the trigger reason and estimated token count.

**Explicitly not in v1:** O2 (chunk + merge) — semantic extraction doesn't merge cleanly. O4 (escalate to higher-tier model) — conflicts with M1's single-model determinism stance.

### 4. Model selection — M1 in v1, M3 path in v1.1

**v1:** A single model (default `claude-sonnet-4-6`, configurable via `Settings.llm_model`) handles all LLM calls. Both Pass 1 and Pass 2 use the same model. Migration-hazard prompts (ADR-008+) inherit the same default.

**v1.1 evolution (M3):** `Settings` will gain per-stage model overrides:
* `llm_model_pass1`, `llm_model_pass2`, `llm_model_hazards`
* Default mapping documented at the time: experimentation phase = Haiku for Pass 1 + Sonnet for Pass 2; production = Sonnet for Pass 1 + Sonnet/Opus for hazards.
* Cache invalidation rule: any model switch within a run resets the cache for that model (each model has its own cache pool). Eval (ADR-017) will need to flag quality drift across model splits.

ADR-005 reserves the `llm_model_*` field names; ADR-014 / ADR-016 fill in the v1.1 detail.

### 5. Concurrency, retries, rate limits

* **Concurrency:** `Settings.llm_concurrency` (default = 5). Pass 1's N calls are dispatched through a bounded async pool of this size.
* **Retries:** rely on the provider SDK's built-in retry for `429` (rate limit) and `529` (overload). Cap explicit retries at 5 per call. Exponential backoff with jitter (SDK default).
* **Per-call failure:** if a single Pass 1 call exhausts retries, skip + record in the run manifest (ADR-022); the rest of the run proceeds. Same shape as ADR-003's parse-failure policy. The graph's affected class is tagged `extraction_mode: llm_failed` and carries only its AST-extracted facts.
* **Run-level failure:** if > 10% of Pass 1 calls fail, abort the run with a clear error. Threshold configurable via `Settings.max_pass1_failure_ratio` (default 0.10). Rationale: graph quality degrades unacceptably past that point; better to fail fast than emit a half-extracted graph.

### 6. Orchestration framework — LangChain with native prompt-cache pass-through (constraint for ADR-013)

* All LLM calls in v1 go through LangChain's provider integrations (`ChatAnthropic`, `ChatBedrockConverse`, etc.).
* Prompt-cache hints are emitted via LangChain's native pass-through — `cache_control={"type": "ephemeral"}` for Anthropic; `cachePoint` for Bedrock Converse via `BedrockPromptCachingMiddleware`.
* **Constraint flagged for ADR-013:** ADR-013's provider-abstraction design must not paper over per-provider cache mechanics. The cache-control parameter must remain reachable so the Pass 1 prefix can be marked.
* **Constraint flagged for v1.1 batch (B2 deferred):** Batch API path will bypass LangChain for submission/polling and re-enter the LangChain structured-output flow on result parse.

### Consequences

* Good, because the cached prefix collapses Pass 1's per-call input cost from ~full-prompt to ~variable-suffix-only after the first call. Typical 5–10× input cost reduction across the project.
* Good, because the O1 default keeps extraction uniform for ~99% of real classes; the O3 escape hatch means no class silently degrades or fails on extreme outliers.
* Good, because M1's single-model stance keeps the v1 graph stylistically uniform for eval — comparing nodes is meaningful.
* Good, because deferring batch keeps v1's implementation lean and contained within LangChain.
* Good, because explicit failure thresholds (per-call skip + ratio-level abort) make the failure mode visible and tunable.
* Bad, because oversized classes that fall into O3 mode have semantically-shallow nodes — eval will need to handle three `extraction_mode` values now (`ast`, `regex_fallback`, `signatures_only`).
* Bad, because LangChain dependency carries weight (transitive deps, churn history); accepted for orchestration value.
* Bad, because v1.1's batch path will involve dropping below LangChain to the Anthropic SDK for that one path. Architectural seam acknowledged.
* Bad, because a single-model stance defers the cost-saving Haiku route to v1.1, paying full Sonnet input cost on every Pass 1 call (mitigated by caching).

### Confirmation

* **Cache-hit unit test:** mock provider; issue 5 Pass 1 calls; assert the cached prefix is sent only once and subsequent calls reference the cache.
* **Oversized-class integration test:** fixture class > 80K-token estimate; assert the prompt sent contains only signatures (no method bodies); assert the resulting node has `extraction_mode: signatures_only`.
* **Concurrency test:** issue 50 concurrent Pass 1 calls with default concurrency = 5; assert at most 5 in flight at any moment.
* **Failure-ratio test:** mock 15% of calls to fail; assert the run aborts with the configured error.
* **Cache-control passthrough test:** snapshot the Anthropic API request payload; assert `cache_control` is present on the cached prefix block.

## Pros and Cons of the Options

### Caching

**C1 — single breakpoint** *(chosen)*
* Good, because trivial implementation; pays off immediately on any project ≥ 4 classes.
* Good, because matches v1's single-target-language run pattern.
* Bad, because zero flexibility for multi-target-language runs (not a v1 use case).

**C2 — two breakpoints**
* Good, because supports per-target-language idiom variation without invalidating system cache.
* Bad, because v1 has no multi-target-language run pattern; second breakpoint is unused budget.

**C3 — no caching**
* Good, because zero implementation work.
* Bad, because Pass 1's input cost compounds linearly with N; on a 200-class project that's ~199× the avoidable cost.

### Sync vs Batch

**B1 — sync only in v1** *(chosen)*
* Good, because keeps v1 within LangChain's covered API surface.
* Good, because matches the interactive-CLI UX users expect.
* Bad, because forfeits 50% discount available via Batch API.

**B2 — sync + `--batch` flag in v1**
* Good, because bulk-mode discount available immediately.
* Bad, because LangChain doesn't wrap Batch API; first multi-path implementation work in v1.

**B3 — auto-batch over threshold**
* Good, because users get discount transparently on big projects.
* Bad, because surprise behaviour; latency change is jarring at threshold crossings.

### Oversized input

**O1 — send whole class always**
* Good, because uniform extraction; modern context windows easily handle typical Spring Boot classes.
* Bad, because attention quality decays on outlier classes (>5K LoC); silent degradation.

**O2 — chunk + merge**
* Good, because never hits context limit.
* Bad, because semantic extraction (intent, hazards, summaries) belongs to the whole, not chunks; merge fails for the LLM's actual job here.
* Bad, because high implementation cost (chunking + overlap + merge + partial-failure handling).

**O3 — signatures-only fallback**
* Good, because deterministic, predictable, low-cost.
* Bad, because lossy on body-level facts (no NL summary of the body, no body-derived hazards).

**O4 — escalate to higher-tier model**
* Good, because best long-context reasoning quality.
* Bad, because conflicts with M1's single-model stance; cache invalidates on model switch; quality drift across the graph.

**O1 default + O3 escape hatch** *(chosen)*
* Good, because uniform behaviour for ~99% of classes; safe degradation only on extreme outliers.
* Good, because no chunking complexity; no model-switch complexity.
* Bad, because eval (ADR-017) gains a third `extraction_mode` to handle.

### Model selection

**M1 — single model** *(chosen for v1)*
* Good, because uniform graph style; clean eval comparison.
* Good, because lowest configuration surface.
* Bad, because pays Sonnet rate on every Pass 1 call; Haiku savings forfeited.

**M2 — tiered (Haiku Pass 1, Sonnet Pass 2)**
* Good, because ~5× cheaper Pass 1 input.
* Bad, because Haiku quality on structured semantic extraction is unproven for this task; v1 lacks eval data to verify.

**M3 — configurable per stage** *(chosen for v1.1)*
* Good, because lets users pick the cost/quality curve per stage.
* Bad, because adds configuration surface; meaningful only after eval framework exists to compare.

### Concurrency

**Default 5, configurable** *(chosen)*
* Good, because conservative default avoids rate-limit surprises on small Anthropic accounts.
* Good, because `Settings.llm_concurrency` lets users on higher-tier accounts dial up.
* Bad, because conservative — leaves throughput on the table for heavy users until they tune it.

### Orchestration

**LangChain with native cache pass-through** *(chosen)*
* Good, because LangChain handles provider switching cleanly (key for ADR-013's abstraction).
* Good, because `cache_control` propagates without writing custom request middleware.
* Bad, because heavy dep with churn history; will need pin discipline.
* Bad, because v1.1 batch path bypasses LangChain — architectural seam acknowledged.

## More Information

**Relationship to ADR-003.** This ADR consumes Pass 1's per-class call shape (class facts + source). It adds a third `extraction_mode` value (`signatures_only`) to the existing `ast` / `regex_fallback` set. ADR-003 needs no revision — `extraction_mode` is already declared an open `Literal` extension point.

**Relationship to ADR-004.** ADR-004's Reference Threshold Table provides Method LoC and class-level guidance. This ADR cites the *class-level token estimate* (not Method LoC alone) as the trigger for O3, with rationale documented in §3.

**Relationship to ADR-013 (LLM provider abstraction).** This ADR commits to LangChain orchestration with native cache pass-through. ADR-013's provider abstraction must:
1. preserve reachability of `cache_control` / `cachePoint` parameters per provider;
2. allow a per-stage model override (for M3 in v1.1) without re-architecting;
3. accept that the v1.1 batch path will partially bypass the abstraction.

**Relationship to ADR-014 (prompt versioning).** Prompt content is out of scope here. ADR-014 owns prompt templates, versioning, and the partition between cached prefix and per-call suffix. ADR-005 reserves the *structure* of the partition (one cache breakpoint, prefix = system + schema + idiom reference); ADR-014 fills it.

**Relationship to ADR-015 (telemetry + response cache).** The response cache (key = prompt hash → response) is a separate concern from the prompt cache (which is provider-side). Both can coexist. ADR-015 owns the response-cache layer.

**Relationship to ADR-022 (run manifest).** Every `extraction_mode: signatures_only`, `extraction_mode: llm_failed`, retry exhaustion, and aborted run reason must land in the run manifest. ADR-022 fills in manifest schema.

**Deferred items (v1.1 or later):**
* Batch API integration (B2 path).
* Per-stage model selection (M3 path).
* Cost-control CLI flags (`--max-cost-usd`, `--budget-warn`) — ADR-016.
* Higher-TTL prompt cache (1-hour) for very large projects.
* Auto-batch detection over class-count thresholds (B3 — likely never; surprise behaviour rejected).

References:
* Anthropic prompt caching — https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
* Anthropic Messages Batches API — https://docs.anthropic.com/en/api/creating-message-batches
* Anthropic rate limits — https://docs.anthropic.com/en/api/rate-limits
* LangChain `ChatAnthropic` cache control — https://python.langchain.com/docs/integrations/chat/anthropic/#prompt-caching
* MADR template — https://github.com/adr/madr
