---
status: accepted
date: 2026-05-17
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-013 — LLM Provider Abstraction

## Context and Problem Statement

Codeograph's LLM pipeline runs three distinct passes — Pass 1 per-node annotation (high fan-out), Pass 2 corpus synthesis (low fan-out, large context), Pass 3 target-language rendering (medium fan-out, file-shaped output). Each pass needs to call an LLM with structured-output enforcement, typed error handling, telemetry hooks, and a response cache. The legacy implementation called LangChain directly from each pass with no abstraction; that hard-coupled call sites to the orchestration framework and left no seam for caching, telemetry, or per-pass policy.

ADR-013 defines a single `LlmProvider` interface that v1 implements over LangChain (per ADR-005 §6) and that v1.1 can extend for batch and streaming workloads. The interface is deliberately small — every cross-cutting concern (caching, telemetry, retry) lives as a wrapper rather than as a base-class method. This keeps the provider class itself SOLID-clean and makes future evolution additive.

Several constraints arrive from upstream:

* **ADR-005 §6** locked LangChain orchestration with native prompt-cache pass-through (`cache_control` for Anthropic, `cachePoint` for Bedrock). ADR-013's provider abstraction must not paper over per-provider cache mechanics; the cache-control parameter must remain reachable so Pass 1's prefix can be marked.
* **ADR-005 §3** locked sync-only LLM calls in v1; Batch API is deferred to v1.1.
* **ADR-007** requires an `--ast-only` mode in the pipeline so golden tests skip LLM passes; the provider abstraction must not be required for AST-only runs.
* **ADR-014** (sibling) defines prompt artefacts with version label and content hash; the provider abstraction carries those through to cache keys and telemetry records.
* **ADR-015** (sibling) defines the response-cache and telemetry shape; ADR-013 supplies the wrapper composition points.

The scope is narrow: this ADR defines the *interface* and *middleware composition pattern* used by every LLM call in v1. Implementation of the cache backend (ADR-015), prompt artefact loading (ADR-014), and downstream concerns (rendering, agentic orchestration) are out of scope.

## Decision Drivers

* **Honor ADR-005 §6.** LangChain is the v1 orchestration framework; the abstraction wraps `BaseChatModel` impls (`ChatAnthropic`, `ChatOpenAI`, `ChatBedrockConverse`).
* **SOLID-clean composition.** Cross-cutting concerns (cache, telemetry, retry) belong in wrappers, not on the provider class itself.
* **Per-pass intent visible at the call site.** Pass 1 (FAST), Pass 2 (DEEP), Pass 3 (RENDER) must be declared per call, not inferred from launch config.
* **Per-provider cache mechanics reachable.** Anthropic ephemeral cache, Bedrock cachePoint — both surface through a single `CacheHint` abstraction.
* **Token accounting accurate enough for cost reports and pre-flight checks.** Pre-flight via local tokenizer; post-call via provider response; drift detection optional.
* **Typed error classification.** Transient (retryable), bad input, auth, content policy, schema validation — five categories the caller branches on cleanly.
* **Concurrent fan-out without forcing async on the world.** Pass 1's 500-class corpus needs concurrency; CLI users and pytest don't need async.
* **Future-friendly.** Batch API (v1.1) and streaming (v1.1) land as additive surfaces, not refactors.

## Considered Options

Each fork below was evaluated against the drivers. Options that were considered and rejected appear in the Pros and Cons section at the end.

### Fork 1 — Abstraction surface

* (a) Provider only (model fixed at construction).
* (b) Provider + model (model per call).
* **(c) Provider + model + tier (Tier enum at call; `override_model` escape hatch). ✅**

### Fork 2 — Sync vs async surface

* (a) Sync only.
* (b) Async only.
* (c) Both (sync wraps async).
* **(d) Sync surface + `complete_structured_many` with uniform internal `ThreadPoolExecutor`. ✅**

### Fork 3 — Pass-separation strategy

* **(a) Flat interface + middleware/decorator pattern with `CallContext`. ✅**
* (b) Distinct ABCs per pass (`Pass1Provider`, `Pass2Provider`, `RenderProvider`).
* (c) Flat interface with `Purpose` enum on the provider call.

### Fork 4 — Streaming support

* (a) Streaming in v1 (full async surface).
* **(b) Defer streaming to v1.1; sync-only structured-output in v1. ✅**
* (c) Reserve `acomplete_streaming` method in v1 raising `NotImplementedError`.

### Fork 5 — Token accounting

* (a) Provider response only (post-call exact, no pre-flight).
* (b) Local tokenizer only (pre-call + post-call exact).
* **(c-trimmed) `TokenUsage` with optional `input_estimated` for drift detection. ✅**
* (d) Heuristic only (char / 4).

### Fork 6 — Failure semantics

* (a) All retries inside the provider; caller sees success or terminal failure.
* (b) Surface raw errors; caller owns retry.
* (c) Hybrid — provider retries transient internally, surfaces semantic.
* **(d) Retry as middleware wrapper; error classification stays in base provider. ✅**

### Fork 7 — `cache_control` segmentation

* (a) Caller constructs messages with provider-specific cache markers inline.
* (b) Provider has explicit `cacheable_prefix` parameter.
* **(c) Per-message `CacheHint(ttl="5m"|"1h")` on `Message`; provider translates to native. ✅**
* (d) Defer to v1.1.

### Fork 8 — Batch API support

* (a) Single interface, batch hidden behind a flag.
* (b) Separate `complete_structured_batch` method on same ABC.
* (c) Separate `BatchLlmProvider` ABC.
* **(d) Defer to v1.1. Future v1.1 shape: separate `BatchLlmProvider` ABC + Style 1 parallel middleware stack. ✅**

### Fork 9 — LangChain dependency

* **(a) Keep LangChain. ✅** (Honors ADR-005 §6.)
* (b) Drop LangChain; use raw provider SDKs.
* (c) Hybrid — LangChain for structured output, raw SDK elsewhere.

## Decision Outcome

### Fork 1 — Abstraction surface: (c) tier + override_model

```python
class Tier(StrEnum):
    FAST = "fast"      # Pass 1 — annotation, high throughput, cheap model
    DEEP = "deep"      # Pass 2 — synthesis, larger model
    RENDER = "render"  # Pass 3 — conversion output, top-tier model

class LlmProvider(ABC):
    @abstractmethod
    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]: ...
```

Tier resolves to a concrete model via a `tier_map` passed at provider construction. The `override_model` escape hatch handles the 1% of calls that need a specific model regardless of tier. Telemetry records both `tier` and `model` so the override is visible in audits.

The provider class accepts the LangChain `BaseChatModel` instance(s) it wraps; the registry lives at construction time in the orchestrator, not as a static lookup.

### Fork 2 — Sync vs async surface: (d) sync + concurrent helper

```python
class LlmProvider(ABC):
    @abstractmethod
    def complete_structured(self, ...) -> LlmResult[T]: ...

    def complete_structured_many(
        self,
        tier: Tier,
        requests: list[tuple[list[Message], type[T]]],
        *,
        max_concurrent: int = 10,
        override_model: str | None = None,
    ) -> list[LlmResult[T]]:
        """Default impl uses ThreadPoolExecutor. Provider-uniform.
        Future v1.x amendment may swap to anyio + native async client
        if rate-limit headroom > 50 concurrent and memory pressure measured."""
        with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
            futures = [
                ex.submit(self.complete_structured, tier, msgs, schema,
                          override_model=override_model)
                for msgs, schema in requests
            ]
            return [f.result() for f in futures]
```

CLI stays sync. pytest stays sync. No `pytest-asyncio` dependency. Concurrency is opaque to the caller; the orchestrator just calls `complete_structured_many` and gets results in input order.

### Fork 3 — Pass separation: (a) flat + middleware

The provider has two methods (single-call + concurrent fan-out). Cross-cutting concerns are wrappers that implement `LlmProvider`:

```python
@dataclass(frozen=True)
class CallContext:
    purpose: Purpose          # ANNOTATE | SYNTHESIZE | RENDER
    prompt_id: str            # from ADR-014
    prompt_version: str       # from ADR-014
    prompt_content_hash: str  # from ADR-014
    corpus_id: str

class Purpose(StrEnum):
    ANNOTATE = "annotate"      # Pass 1
    SYNTHESIZE = "synthesize"  # Pass 2
    RENDER = "render"          # Pass 3

class CachingLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, cache: ResponseCache, ctx: CallContext): ...

class TelemetryLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, emitter: TelemetryEmitter, ctx: CallContext): ...

class RetryingLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, policy: RetryPolicy): ...
```

Wrapper composition (outer → inner): **Telemetry → Caching → Retry → Provider**. Telemetry sees the final outcome including retries; cache hits skip retry; the provider itself stays minimal.

Each pass orchestrator builds its own stack with its own `CallContext` (different `purpose`, possibly different cache/retry policy).

### Fork 4 — Streaming: (b) defer to v1.1

v1 ships sync structured-output only. Pass 3 long renders show a per-file progress bar ("rendering 3/24 files…") instead of token-level streaming. v1.1 will add `acomplete_streaming` as a *new* method on the abstraction; sync core remains unchanged. No interface debt accrues by waiting.

### Fork 5 — Token accounting: (c-trimmed) TokenUsage + optional estimate

```python
@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int           # provider response.usage (exact, billing source)
    output_tokens: int          # provider response.usage
    cached_tokens: int          # Anthropic prompt-cache hits (0 if N/A)
    input_estimated: int | None = None  # populated only if count_tokens was called

@dataclass(frozen=True)
class LlmResult(Generic[T]):
    value: T
    usage: TokenUsage
    model: str
    latency_ms: int

class LlmProvider(ABC):
    @abstractmethod
    def count_tokens(self, messages: list[Message]) -> int:
        """Pre-flight token count (local tokenizer via LangChain pass-through).
        Required for budget checks and chunking."""

    @abstractmethod
    def complete_structured(self, ...) -> LlmResult[T]: ...
```

Pre-flight budget enforcement uses the estimate; cost reports use the actual; ADR-015 telemetry records the drift (`input_estimated − input_tokens`) for tokenizer-aging detection.

### Fork 6 — Failure semantics: (d) middleware retry + base classification

The base provider classifies SDK errors into a typed exception tree:

```python
class LlmError(Exception): pass
class LlmTransientError(LlmError): pass          # network, 429, 5xx — retry candidate
class LlmBadInputError(LlmError): pass           # 400 — surface
class LlmAuthError(LlmError): pass               # 401/403 — surface
class LlmContentPolicyError(LlmError): pass      # policy violation — surface
class LlmSchemaValidationError(LlmError): pass   # response didn't parse — surface
class LlmRateLimitExhausted(LlmTransientError):  # after wrapper's retries exhausted
    pass
```

`RetryingLlmProvider` wraps a base provider and retries only `LlmTransientError`. Bad-input, auth, content-policy, and schema-validation errors pass through to the caller, which makes a decision (degrade this node, abort run, etc.).

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_s: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_s: float = 30.0
    respect_retry_after_header: bool = True
```

Per-pass retry tuning is data, not code — Pass 1 (high-volume, expects transients) uses a more generous policy; Pass 3 (low-volume, fail-fast) uses a strict one.

### Fork 7 — cache_control: (c) per-message CacheHint

```python
@dataclass(frozen=True)
class CacheHint:
    ttl: Literal["5m", "1h"] = "5m"

@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str
    cache: CacheHint | None = None
```

Each provider translates `CacheHint` to native: Anthropic emits `additional_kwargs={"cache_control": {"type": "ephemeral", "ttl": ...}}`; Bedrock emits `cachePoint`; providers without native cache ignore the hint. The Anthropic provider warns when a segment marked `cacheable` is below the 1024-token minimum where the cache offers no benefit.

Up to four cacheable segments per request (Anthropic's limit). Typical Pass 1 shape:

```python
messages = [
    Message(role="system", content=SYSTEM_PROMPT,    cache=CacheHint()),
    Message(role="system", content=GRAPH_SCHEMA_DOC, cache=CacheHint()),
    Message(role="system", content=SOURCE_BLOCK,     cache=CacheHint(ttl="1h")),
    Message(role="user",   content=f"Annotate node {node_id}"),
]
```

### Fork 8 — Batch API: (d) defer to v1.1

v1 ships live methods only (`complete_structured`, `complete_structured_many`). The v1.1 design is captured here as future work:

**v1.1 target shape — separate `BatchLlmProvider` ABC with Style 1 parallel middleware stack.**

```python
# v1.1 only — not in v1
class BatchLlmProvider(ABC):
    def submit_batch(self, tier, requests, ...) -> BatchJobId: ...
    def poll_batch(self, job_id: BatchJobId) -> BatchStatus: ...
    def retrieve_batch(self, job_id: BatchJobId) -> list[LlmResult[T]]: ...
    def complete_structured_batch(self, tier, requests, ...) -> list[LlmResult[T]]: ...

class AnthropicProvider(LangChainLlmProvider, BatchLlmProvider): ...
class OpenAIProvider(LangChainLlmProvider, BatchLlmProvider): ...

class BatchCachingLlmProvider(BatchLlmProvider): ...
class BatchTelemetryLlmProvider(BatchLlmProvider): ...
class BatchRetryingLlmProvider(BatchLlmProvider): ...
```

Parallel stack — Style 1 — gives compile-time enforcement of "you cannot wrap a non-batch provider in a batch middleware." ADR-005 §3 already acknowledged the v1.1 batch path partially bypasses LangChain at the submit/poll/retrieve level; the structured-output result-parse re-enters the LangChain flow.

### Fork 9 — LangChain: (a) keep

v1 providers are LangChain-based:

```python
class LangChainLlmProvider(LlmProvider):
    """Base provider wrapping any LangChain BaseChatModel."""

    def __init__(
        self,
        chat_model: BaseChatModel,
        tier_map: dict[Tier, str],
        ...,
    ):
        self._chat = chat_model
        self._tier_map = tier_map

    def complete_structured(
        self, tier, messages, schema, *, override_model=None, max_tokens=4096,
    ) -> LlmResult[T]:
        # 1. Resolve model from tier_map (or override).
        # 2. Translate Message + CacheHint to LangChain BaseMessage with
        #    additional_kwargs={"cache_control": {"type": "ephemeral", "ttl": ...}}.
        # 3. chain = self._chat.with_structured_output(schema)
        # 4. Invoke chain; catch SDK errors and classify into LlmError taxonomy.
        # 5. Wrap result + usage_metadata into LlmResult[T].

class AnthropicProvider(LangChainLlmProvider):
    def __init__(self, api_key, tier_map, ...):
        chat = ChatAnthropic(api_key=api_key, ...)
        super().__init__(chat, tier_map, ...)

class OpenAIProvider(LangChainLlmProvider): ...
class BedrockProvider(LangChainLlmProvider): ...  # ChatBedrockConverse
```

LangChain provides the structured-output tool-use plumbing, the tokenizer pass-through (Fork 5's `count_tokens`), and the message-formatting layer. Provider-specific quirks (Anthropic `cache_control` vs Bedrock `cachePoint`) are handled by each concrete provider's `_translate_messages` method.

### `--ast-only` mode (constraint from ADR-007)

ADR-007 requires the pipeline to support `--ast-only` (or `--no-llm`). When enabled, the orchestrator skips Pass 1 / Pass 2 entirely; no `LlmProvider` is instantiated; `llm-annotations.json` is not emitted. The provider abstraction is unaffected — it simply isn't called. CLI flag wired into `codeograph annotate --ast-only`.

## Consequences

**Positive.**

* Single interface across providers; tier-based intent visible at every call.
* Cross-cutting concerns (cache, telemetry, retry) compose as wrappers — provider class stays minimal and SOLID-clean.
* Each pass orchestrator builds its own wrapper stack with its own `CallContext`; per-pass policy is data, not code.
* Typed error tree lets callers branch cleanly — "degrade this node" vs "abort run" is explicit.
* Token accounting supports both pre-flight checks (chunking, budget) and post-call billing reconciliation.
* `CacheHint` abstracts per-provider cache mechanics; Anthropic ephemeral cache reachable without leaking provider-specific JSON to call sites.
* Pre-flight tokenizer-drift detection (input_estimated vs actual) catches provider tokenization changes early.
* Honors ADR-005 §6 LangChain commitment; existing prompt-cache pass-through pattern is preserved.
* **Reversibility from LangChain.** The LangChain dependency is structurally isolated to `LangChainLlmProvider`. Downstream code (orchestrators, middleware wrappers, tests) depends only on the abstract `LlmProvider` interface. Concrete providers MAY hold a raw SDK client in addition to the LangChain wrapper when v1.1+ features (batch, streaming, mid-run model switching) need to bypass LangChain. Replacing LangChain entirely in v1.1+ requires reimplementing concrete providers (~150 LOC each); no caller-side changes are required.
* Sync surface keeps CLI, pytest, and integration code straightforward — no `pytest-asyncio` tax.
* v1.1 batch and streaming land as additive surfaces, not refactors — no interface debt accumulates by deferring.
* `--ast-only` mode (per ADR-007) is trivially supported — orchestrator simply doesn't instantiate any `LlmProvider`.

**Negative.**

* Wrapper composition is a pattern contributors must learn; bare `LlmProvider` use in tests is encouraged via a `build_default_stack(...)` helper to mitigate.
* LangChain is a heavy dependency (transitive package count, occasional churn); accepted for orchestration value per ADR-005.
* v1.1 batch path will partially bypass LangChain at the submit/poll/retrieve level — architectural seam acknowledged in ADR-005 §3 and re-acknowledged here.
* Adding a new provider requires understanding LangChain's `BaseChatModel` contract and the cache-control translation pattern; documented in `CONTRIBUTING.md`.
* `CallContext` is a small dataclass passed to every wrapper at construction; growth into a god-bag is a known risk flagged in the Open Questions section below.
* Per-pass retry/cache policy must be wired explicitly by the orchestrator; getting it wrong is a silent-quality issue rather than a hard error.

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. **`LlmProvider` ABC exists** at `codeograph/llm/provider.py` with the two abstract methods (`complete_structured`, `count_tokens`) and the default `complete_structured_many` impl.
2. **`Tier`, `Purpose`, `CallContext`, `CacheHint`, `Message`, `LlmResult`, `TokenUsage`** types defined at `codeograph/llm/types.py`.
3. **Typed error tree** (`LlmError` family) at `codeograph/llm/errors.py`.
4. **`LangChainLlmProvider` base** at `codeograph/llm/providers/langchain_base.py` with concrete `AnthropicProvider`, `OpenAIProvider`, `BedrockProvider` subclasses.
5. **Middleware wrappers** (`CachingLlmProvider`, `TelemetryLlmProvider`, `RetryingLlmProvider`) at `codeograph/llm/middleware/` — each in its own file per the project's one-class-per-file convention.
6. **`build_default_stack(...)` helper** at `codeograph/llm/factory.py` for constructing the standard `Telemetry → Caching → Retry → Provider` stack.
7. **Pipeline supports `--ast-only`** — CLI flag is wired, Pass 1 / Pass 2 short-circuit, `llm-annotations.json` is not emitted.
8. **Unit tests** for each wrapper cover the cache-hit / cache-miss / retry / error-classification paths against mock providers.
9. **Integration test** confirms a Pass 1 call through the full stack (Telemetry → Cache miss → Retry on transient → Anthropic provider) succeeds end-to-end against a recorded fixture (no live API call in CI).

## Pros and Cons of the Considered Options

### Fork 1 — Abstraction surface

**(a) Provider only.**
* Good, because minimal interface; one instance per (provider, model) pair.
* Bad, because every model change needs a new provider instance; tier semantics implicit.
* Bad, because doesn't fix the legacy "tier via launch config" foot-gun.

**(b) Provider + model.**
* Good, because single provider instance, many models.
* Bad, because tier semantics still implicit; caller has to remember which model is the cheap one.
* Bad, because provider swap touches every call site.

**(c) Provider + model + tier with `override_model`. ✅ Chosen.**
* Good, because tier declared at every call site — intent visible.
* Good, because provider swap is one config block.
* Good, because telemetry naturally tags `tier`.
* Good, because escape hatch (`override_model`) handles the rare per-call need.
* Bad, because one more abstraction layer; tier taxonomy must be defined upfront.

### Fork 2 — Sync vs async

**(a) Sync only.**
* Good, because simplest mental model.
* Bad, because Pass 1 over 500 nodes is ~17 min sequential.

**(b) Async only.**
* Good, because efficient concurrency.
* Bad, because every caller becomes async; `pytest-asyncio` everywhere; CLI tax.

**(c) Both (sync wraps async).**
* Good, because aesthetic flexibility.
* Bad, because `asyncio.run()` from sync foot-guns in any nested event loop.

**(d) Sync + `complete_structured_many` with internal ThreadPool. ✅ Chosen.**
* Good, because honors sync caller surface; CLI/tests stay sync.
* Good, because concurrency hidden inside the helper; one primitive, swappable.
* Good, because future swap to anyio is a single-file change, no caller impact.
* Bad, because two methods to implement per provider (mitigated by default helper impl).

### Fork 3 — Pass separation

**(a) Flat interface + middleware. ✅ Chosen.**
* Good, because SOLID-clean — provider does one thing.
* Good, because cross-cutting concerns are composable wrappers.
* Good, because `CallContext` carries pass-specific metadata into cache/telemetry.
* Good, because adding a new pass requires zero provider changes.
* Bad, because wrapper composition is a pattern contributors must learn.

**(b) Per-pass ABCs.**
* Good, because compile-time tier enforcement.
* Bad, because god-object provider implementing multiple unrelated interfaces.
* Bad, because adding a pass means new ABC + N provider edits.

**(c) `Purpose` enum on provider call.**
* Good, because purpose visible in telemetry without extra wrapper.
* Bad, because OCP violation — new pass purpose = modify every provider's policy table.
* Bad, because borderline SRP — provider knows pass semantics, a layer concern.

### Fork 4 — Streaming

**(a) Streaming in v1.**
* Good, because best CLI responsiveness on long renders.
* Bad, because contradicts Fork 2's sync caller surface.
* Bad, because structured-output + streaming is awkward (Pydantic validation needs full response).

**(b) Defer to v1.1. ✅ Chosen.**
* Good, because honors Fork 2 lock; structured-output stays clean.
* Good, because retrofit is purely additive (new `acomplete_streaming` method).
* Good, because no `pytest-asyncio` tax in v1.
* Bad, because CLI shows a spinner on long Pass 3 renders (mitigable with per-file progress bar).

**(c) Reserve method raising `NotImplementedError`.**
* Good, because interface stable across v1 → v1.1.
* Bad, because abstract method that raises is a code smell.
* Bad, because forces `pytest-asyncio` for any test touching it.

### Fork 5 — Token accounting

**(a) Provider response only.**
* Good, because exact billing counts.
* Bad, because no pre-flight; can't refuse oversized requests before sending.

**(b) Local tokenizer only.**
* Good, because pre-flight works.
* Bad, because tokenizer drift vs server-side count is unmonitored.

**(c-trimmed) `TokenUsage` with optional `input_estimated`. ✅ Chosen.**
* Good, because pre-flight enforced via `count_tokens`.
* Good, because billing-accurate via response usage.
* Good, because optional drift telemetry catches tokenizer aging early.
* Good, because cache key uses input hash, not token count — Option C's "fuzzy cache key" concern doesn't apply.
* Bad, because two fields to thread through (mitigated by `TokenUsage` dataclass).

**(d) Heuristic only.**
* Good, because zero deps.
* Bad, because ±20% error; legacy anti-pattern.

### Fork 6 — Failure semantics

**(a) All retries inside provider.**
* Good, because caller code clean.
* Bad, because retry behavior opaque; pass-specific tuning hard.

**(b) Surface raw errors; caller owns retry.**
* Good, because maximum flexibility.
* Bad, because every caller reimplements retry; drift inevitable.

**(c) Hybrid — provider retries transient, surfaces semantic.**
* Good, because best of both.
* Bad, because doesn't compose with Fork 3's middleware pattern; retry policy stuck in provider class.

**(d) Retry as middleware wrapper + base classification. ✅ Chosen.**
* Good, because composes with Fork 3 (cache/telemetry/retry are all wrappers).
* Good, because classification (SDK error → typed `LlmError`) stays with the SDK call; wrapper applies uniform policy.
* Good, because pass-specific retry tuning is data passed at construction.
* Good, because cache hits skip retry naturally (composition order: Telemetry → Caching → Retry → Provider).
* Bad, because six typed exception classes to design and document (one-time taxonomy work).

### Fork 7 — cache_control

**(a) Inline cache markers in messages.**
* Good, because direct provider mapping.
* Bad, because Anthropic-specific leak in the caller's message construction.

**(b) Provider has `cacheable_prefix` parameter.**
* Good, because two-segment model is simple.
* Bad, because rigid; doesn't support Anthropic's 4-breakpoint capability cleanly.

**(c) Per-message `CacheHint(ttl)`. ✅ Chosen.**
* Good, because provider-neutral (`cacheable=True` is meaningful across providers).
* Good, because supports up to N cacheable segments naturally.
* Good, because TTL extension (`5m` default, `1h` opt-in) accommodates Anthropic's 1-hour cache without future re-design.
* Good, because provider impl can warn on undersized cacheable segments.
* Bad, because boolean granularity (cacheable yes/no) doesn't capture per-segment TTL differences — partially addressed via the TTL field.

**(d) Defer to v1.1.**
* Good, because v1 interface stays minimal.
* Bad, because legacy showed the "3x source block per chunk" cost; deferring leaves the ~90% discount on the table.

### Fork 8 — Batch API

**(a) Single interface, batch hidden behind a flag.**
* Good, because one method to call.
* Bad, because sync method that might sleep for hours is a foot-gun for any CLI usage.

**(b) Separate method on same ABC.**
* Good, because latency profile visible at call site.
* Bad, because `NotImplementedError` default smells of LSP violation.

**(c) Separate ABC (parallel middleware stack).**
* Good, because compile-time capability enforcement.
* Good, because SOLID-clean.
* Bad, because doubles middleware classes; ~625 LOC initial cost.

**(d) Defer to v1.1; future shape = (c) + Style 1. ✅ Chosen.**
* Good, because honors ADR-005 §3 sync-only v1.
* Good, because v1.1 shape is documented here as future work; migration is purely additive.
* Good, because zero LSP/ISP debt accrues by deferring.
* Bad, because v1 forfeits the 50% Pass 1 cost discount until v1.1 lands.

### Fork 9 — LangChain dependency

**(a) Keep LangChain. ✅ Chosen.**
* Good, because honors locked ADR-005 §6 commitment.
* Good, because `with_structured_output`, `count_tokens`, and message-formatting are off-the-shelf.
* Good, because adding a new provider is "add the `langchain-{provider}` dep and register class path."
* Bad, because heavy transitive dep tree (~30+ packages, ~80 MB install).
* Bad, because LangChain version churn requires pin discipline; periodic Tuesday afternoon spent reconciling.
* Bad, because LCEL and chain abstractions we don't use are dead weight (mitigated: don't use them).

**(b) Drop LangChain; use raw SDKs.**
* Good, because minimal deps; faster import; smaller install.
* Good, because direct control of cache_control, batch API, error classification.
* Bad, because contradicts ADR-005 §6 — would require reopening that lock.
* Bad, because ~150 LOC per provider to reimplement what LangChain handles.

**(c) Hybrid — LangChain for structured output only.**
* Good, because reuses the most-credited LangChain feature.
* Bad, because double-dependency; two error surfaces; architectural smell.

## More Information

**Relationships to other ADRs.**

* **ADR-005 §3** locked sync-only LLM calls in v1; ADR-013 Fork 4 (streaming defer) and Fork 8 (batch defer) honor this.
* **ADR-005 §6** locked LangChain orchestration with native cache pass-through; ADR-013 Fork 9 (keep LangChain) and Fork 7 (`CacheHint` translation) honor this.
* **ADR-007** requires `--ast-only` mode in the pipeline; ADR-013's provider abstraction is unaffected by AST-only runs (orchestrator simply doesn't instantiate any provider).
* **ADR-014** (sibling) defines the prompt artefact format; `CallContext` carries `prompt_id`, `prompt_version`, `prompt_content_hash` from ADR-014 into every wrapper.
* **ADR-015** (sibling) defines the cache backend and telemetry schema; ADR-013 supplies the wrapper composition points (`CachingLlmProvider`, `TelemetryLlmProvider`).
* **ADR-016** (cost-control CLI flags, v1.1) will extend `LlmProvider` with budget-cap parameters; the `override_model` and `max_tokens` parameters are the seam.
* **ADR-017** (eval framework) will exercise the `LlmProvider` interface via mock implementations; the small ABC surface makes mocking trivial.

**Deferred items.**

* **Streaming** (Fork 4) — `acomplete_streaming` method added in v1.1 as a new abstract method; concrete providers opt in. Sync core unchanged.
* **Batch API** (Fork 8) — `BatchLlmProvider` ABC + Style 1 parallel middleware stack added in v1.1; concrete providers (Anthropic, OpenAI) implement both `LlmProvider` and `BatchLlmProvider`.
* **anyio swap for `complete_structured_many`** (Fork 2 consequence) — measured trigger: rate-limit headroom > 50 concurrent and memory pressure observed.
* **Cost-control CLI flags** (ADR-016, v1.1) — `--max-cost-usd`, `--max-tokens-per-call` plumbing.
* **Multi-model tiering within a single pass** (ADR-005 §M3, v1.1) — provider-side fallback (Sonnet → Haiku on transient overload).

**Open questions for future review.**

The following questions should be revisited once concrete LLM-pass implementation has been exercised:
1. Did `LlmProvider` stay minimal, or did `complete_structured` grow extra parameters?
2. Did the middleware stack stay composable (Telemetry → Caching → Retry → Provider)?
3. Did `CallContext` grow into a god-bag?
4. Did the `build_default_stack(...)` helper get used, or did orchestrators build their own stacks ad-hoc?
5. Did the typed error tree's five categories prove sufficient, or did edge cases force new types?

**References.**

* MADR template — https://github.com/adr/madr
* LangChain `BaseChatModel` — https://python.langchain.com/docs/concepts/#chat-models
* LangChain structured output — https://python.langchain.com/docs/how_to/structured_output/
* LangChain `ChatAnthropic` cache control — https://python.langchain.com/docs/integrations/chat/anthropic/#prompt-caching
* Anthropic prompt caching — https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
* Anthropic Messages Batches API — https://docs.anthropic.com/en/api/creating-message-batches (v1.1 reference)
* OpenAI Batch API — https://platform.openai.com/docs/guides/batch (v1.1 reference)
* Python `concurrent.futures.ThreadPoolExecutor` — https://docs.python.org/3/library/concurrent.futures.html

## Amendments

**2026-06-20 — DC2 design-review pass (3 decisions + 2 doc-syncs).** A code-blind design review of ADR-013 (DC2 cluster, guideline 06) produced three locked decisions and two description-level corrections, recorded here.

1. **v1 provider set = Anthropic + OpenRouter (D-013-1).** Fork 9's provider roster is amended: **v1 ships Anthropic + OpenRouter, both mandatory**; Ollama and Bedrock move to **v1.1**. OpenRouter is an active end-of-v1 requirement (cheaper / free aggregated models); plan §4 FR-8 is updated to this real v1 set. **Sub-rule — free-form model pass-through:** the OpenRouter provider config must accept **any** OpenRouter model identifier the user supplies (`<vendor>/<model>` pass-through), NOT an enum of codeograph-blessed constants. Consequently Fork 1's `tier_map`/`override_model` must accept arbitrary OpenRouter model ids, and ADR-001's `llm_model`/`openrouter_*` settings are free `str` fields with no `Literal` allowlist (see the ADR-001 amendment of the same date). The OpenRouter provider implementation is the learner's in-flight work.

2. **Concurrent fan-out partial-failure shape (D-013-3).** Fork 2's `complete_structured_many` is amended to return **per-item results-or-errors** (a result/error wrapper per item) rather than a flat `list[LlmResult]` that re-raises on the first non-retryable failure. This lets the Pass-1 orchestrator honour ADR-005 §5 ("skip the node, record, continue") cleanly instead of pushing per-future discipline onto every caller.

3. **Fan-out concurrency default 10 → 5 (D-013-4).** Fork 2's ABC default `max_concurrent=10` is aligned to **5**, matching ADR-005's locked Pass-1 concurrency. `Settings.llm_concurrency` still overrides.

**Cross-reference:** the provider-credential → env-var extensibility gap (ADR-013 finding #2 / dev DC1-08) is owned by **ADR-001 D-001-1** (a Settings/config concern that already owns env-var naming), not here — see the ADR-001 amendment of the same date. This ADR's "adding a provider is one config block" claim depends on that dynamic alias resolution.

**Doc-syncs (no decision):** Confirmation #1 ("two abstract methods") is corrected — the ABC has a third abstract method `resolve_model`, the cache-key seam (F-013-5); `CallContext` god-bag creep is noted against Open-Question #3 (`provider_name` added first) (F-013-6).

**New Confirmation items (from this amendment):**
* `complete_structured_many` with 1 of N items failing returns N−1 results plus the failure surfaced per-item — not a whole-batch raise (D-013-3).
* The ABC default `max_concurrent` is 5 (D-013-4).
* OpenRouter accepts an arbitrary model-id string with no allowlist rejection (D-013-1 pass-through).

No locked design decision is reversed; the v1 provider roster is re-scoped (OpenRouter added; Ollama/Bedrock deferred to v1.1). Clarification and additive evolution only.

**2026-06-29 — v1 provider expansion (1 decision).** The v1 provider roster is widened from {Anthropic, OpenRouter} to additionally cover **API-key, OpenAI-compatible endpoints** reachable by base-URL configuration. Surfaced while scoping ADR-027 (proper cost validation in v1 needs the cheap/free tiers in `docs/model-selection-and-cost.md` reachable). No locked fork is reversed; Fork 9 (keep LangChain) and D-013-1 (roster growth = amendment) stand.

**D-013-7 — generalize the OpenAI-compatible provider (no allowlist).** Fork 9's concrete provider set is amended: the OpenRouter-specific `OpenRouterProvider` is generalized into a **configurable OpenAI-compatible provider** (`OpenAICompatibleProvider`) whose **base URL is a constructor parameter**, not a hardcoded constant. The one OpenRouter-specific line (`_OPENROUTER_BASE_URL`) becomes configuration, so **any** OpenAI-compatible API-key endpoint is reachable in v1 by setting a base URL, **without a new provider class per vendor and without a coded vendor list.** `ChatOpenAI` over LangChain is retained (Fork 9), and free-form model pass-through (any model id, no `Literal` allowlist) extends from D-013-1.

* **No allowlist — examples are documentation only.** Gemini, Groq, and DeepSeek are the verified starter examples in `docs/model-selection-and-cost.md`; MiniMax, Moonshot, Z.ai, Qwen, Mistral, Together, Fireworks — and OpenAI/GPT itself — also work by construction. Nothing in code enumerates them.
* **OpenRouter retained as a preset.** `OpenRouterProvider` becomes a thin subclass of `OpenAICompatibleProvider` presetting the OpenRouter base URL — OpenRouter stays a mandatory, named v1 provider (D-013-1) and existing config/tests are unaffected. (Exact class naming is an implementation detail; `OpenAICompatibleProvider` recommended.)
* **Scope guard.** This covers only the **API-key, OpenAI-compatible** family. **Ollama and Bedrock stay v1.1** — their `NotImplementedError` stubs in `resolver.py` are unchanged; they need non-OpenAI-compat clients (`ChatBedrockConverse`, Ollama) and are out of scope here.
* **Endpoint identity (provider label).** The generic provider derives a **provider label** — an explicit `CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL` if the user sets one, else the normalized base-URL host — and threads it through the `provider` token in the cache key (FR-17 / ADR-015) and telemetry (FR-16). This keeps the *same model id served by different endpoints* distinct: no cross-host cache collision, no lost audit. ADR-027's price lookup reuses the same label (its 2026-06-29 amendment).
* **Structured-output compatibility is assumed, not guaranteed.** The generic provider relies on the `with_structured_output` / tool-use mechanism (Fork 5); OpenAI-*compatibility* is partial across hosts, so an endpoint that does not honour it surfaces the existing `LlmSchemaValidationError` (Fork 6) with a hint that the endpoint may not support structured output. Verify a new endpoint on a few classes before a full run (cost doc §8).
* **Caching where supported.** `cache_control` pass-through lives in the shared base (`langchain_base.py`); endpoints that support prompt caching inherit it. Support varies across hosts — its absence degrades **cost only, never capability** — so ADR-005 §6's "`cache_control` must stay reachable" remains satisfied wherever the endpoint offers caching.
* **Credential / base-URL / label config is owned in ADR-001** (D-001-5). This ADR's "adding a provider is one config block" claim depends on that resolution.

**New Confirmation items (from this amendment):**
* The OpenAI-compatible provider accepts a **configurable base URL**; pointing it at a new OpenAI-compatible endpoint needs **no new provider class and no code change** (D-013-7).
* The `provider` token = explicit label else base-URL host; it appears in the cache key and telemetry, so two hosts serving the same model id do not collide.
* An endpoint that rejects structured output surfaces `LlmSchemaValidationError` with an endpoint-compatibility hint — not a silent failure.
* `OpenRouterProvider` resolves as a preset of the generic provider; `ProviderType.OPENROUTER` behaviour is unchanged.
* Ollama/Bedrock still raise `NotImplementedError` in v1 (scope guard unchanged).

No locked decision reversed; the v1 provider family is widened to base-URL-configurable OpenAI-compatible endpoints. Additive re-scope only.
