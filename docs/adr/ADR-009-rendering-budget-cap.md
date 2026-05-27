---
status: accepted
date: 2026-05-26
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-009 — Rendering Budget Cap with Stratified Class Selection

## Context and Problem Statement

The knowledge graph covers every class in the source corpus; rendering does not. Spring Boot codebases evaluated by this tool routinely contain hundreds of classes across tens of domains. Without an explicit cap, a single `codeograph run` invocation could trigger hundreds of LLM render calls on the first execution — slow, expensive, and not what an evaluator looking at the tool's quality wants to wait for.

The cap exists to support a **representative-sample preview** of the renderer's output across the full difficulty spectrum of the corpus, not as a cost guardrail. An evaluator looking at three rendered classes from a domain should see one easy case, one typical case, and one hard case — so the rendered sample reads as a fair cross-section of what the tool would produce on a full run. A naive "top N by complexity" selection would only show hard cases and hide the routine ones, defeating the preview purpose.

This ADR decides:
1. Which pipeline component owns the selection logic (so the renderer's contract from ADR-008 stays focused on translation).
2. How classes are sampled within a domain when the cap binds (stratified strategy with cited complexity thresholds).
3. How the corpus is partitioned into domains for the per-domain cap (deterministic grouping that works on every Java project).
4. How the user is informed that the cap bound (so a 3-class output is not mistaken for a full run).

The selection logic must be deterministic and reproducible per FR-14 — same input, same cap, same selection. The full audit trail (selected, skipped, strategy fired per domain, thresholds used) must persist so any scorecard reader can interpret the rendered set in context.

## Decision Drivers

* **Determinism / determinism boundary clarity** — selection runs entirely on deterministic graph data; no LLM judgment in v1 drives which classes are rendered
* **Citation discipline** — bucketing thresholds cite Lanza & Marinescu (2006), the same source ADR-004 §201 forward-referenced for this ADR
* **Tractable v1 implementation** — selection is a pure transformation; one component, no LLM dependency, fully unit-testable
* **YAGNI** — global-scope sampling, LLM-tagged domain selection, and CI-strict mode are deferred to later ADRs with clear triggers
* **Readability as a curated artefact** — `SelectionResult` audit fields let scorecards self-explain ("3 of 47 rendered; strategy=stratified_threshold_v1; missing 'low' bucket")
* **No silent failures** — the user sees at run start that they are in preview mode AND at run end which domains rendered what fraction
* **SOLID-clean composition** — the renderer takes a fully-prepared subgraph from the selector; selection logic is not duplicated across renderers
* **Future Neo4j compatibility** — selection produces a filtered class-id set; the graph shape itself is not mutated by selection

## Considered Options

### Fork 1+2 — Selection placement and sampling strategy (combined)

Selection placement and sampling strategy were locked together because the chosen strategy (stratified bucketing with empty-bucket handling, named strategy versioning, audit fields) makes the selection logic too substantial to live anywhere other than its own component.

**Placement sub-options:**

* **(a) pipeline-layer `ClassSelector` component returning a `SelectionResult` audit artefact; renderer consumes the filtered subgraph. ✅**
* (b) renderer-layer — `Renderer.render()` takes a `cap` parameter and applies it internally.
* (c) graph-annotation layer — Pass 2 (or a new selection pass) writes `render_selected: bool` per class node.
* (d) inline in the CLI — `cli/main.py` does the filter directly before calling the renderer.

**Sampling-strategy sub-options:**

* (α) quantile-based — sort by composite complexity, pick top third / middle third / bottom third.
* (β) threshold-based bucketing — bucket classes high/medium/low using cited Lanza & Marinescu thresholds; pick `N/3` from each bucket.
* **(γ) bucket-by-threshold + rank-within-bucket + tiered strategy ladder — `take_all` (n≤cap) → `top_n_v1` (cap<n<2·cap) → `stratified_threshold_v1` (n≥2·cap); bucketing uses OR-high (`CBO≥5 OR WMC≥20`) and AND-low (`CBO≤1 AND WMC≤5`), Lanza & Marinescu (2006). ✅**

### Fork 3 — Domain definition

* (a) Maven module name from `pom.xml`.
* (b) package-prefix heuristic — first package segment below the longest common base.
* (c) LLM-tagged domains from Pass 2 corpus synthesis.
* (d) explicit user-provided mapping (config file with `pattern → domain` rules).
* **(e) hybrid — package-prefix heuristic (b) as default; explicit mapping (d) as opt-in override; LLM-tagged grouping (c) reported in scorecards but does NOT drive selection in v1. ✅**

### Fork 4 — Cap-exceeded behavior

* (a) silent truncation; manifest carries the audit.
* **(b) INFO log at run start (printing cap value and the `--max-classes-per-domain 0` escape) + per-run summary table at run end + manifest audit always authoritative. ✅**
* (c) WARN per domain whenever the cap binds.
* (d) (b) plus an opt-in `--strict-cap` flag that fails CI when the cap binds and the user did not explicitly pass the flag.
* (e) (b) plus a `RENDERED.md` summary file written to the output directory.

## Decision Outcome

### Fork 1+2 — Selection placement and sampling strategy: (a) `ClassSelector` + (γ) bucket-rank-ladder

A dedicated `ClassSelector` component sits between graph assembly and rendering. It consumes the full graph plus LLM annotations and returns a `SelectionResult` audit artefact. The pipeline applies the result by subsetting the graph to the selected class ids before calling the renderer.

```python
# codeograph/rendering/class_selector.py
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class SelectionResult:
    selected:            dict[str, list[ClassId]]              # domain -> class ids
    skipped:             dict[str, list[ClassId]]
    bucket_membership:   dict[ClassId, Literal["high","medium","low"]]
    empty_buckets:       dict[str, list[str]]                  # domain -> ["low", ...]
    cap:                 int | None                            # None = unlimited
    scope:               Literal["per_domain", "global"]
    strategy_per_domain: dict[str, str]                        # named strategy per domain
    thresholds_used:     dict[str, tuple[int, int]]            # {"cbo": (1, 5), "wmc": (5, 20)}


class ClassSelector:
    def __init__(
        self,
        cap: int | None,
        scope: Literal["per_domain", "global"] = "per_domain",
        thresholds: dict[str, tuple[int, int]] | None = None,
        domain_grouping: DomainGrouping | None = None,
    ) -> None:
        self._cap = cap
        self._scope = scope
        self._thresholds = thresholds or {"cbo": (1, 5), "wmc": (5, 20)}
        self._domain_grouping = domain_grouping or PackagePrefixGrouping()

    def select(
        self,
        graph: CodeographKnowledgeGraph,
        annotations: LlmAnnotations,
    ) -> SelectionResult: ...
```

**Strategy ladder per domain.** When `select()` runs on a single domain with `n` classes and cap `N`, it picks the strategy by size and records the choice in `SelectionResult.strategy_per_domain` so scorecards explain themselves:

| Condition | Strategy name | Behavior |
|---|---|---|
| `n ≤ N` | `take_all` | Return all classes; cap does not bind. |
| `N < n < 2·N` | `top_n_v1` | Sort by composite (`CBO + 0.5·WMC`, then alphabetical); take top `N`. Stratification would waste slots when the domain is too small to bucket meaningfully. |
| `n ≥ 2·N` | `stratified_threshold_v1` | Bucket by threshold rule; sort within each bucket; round-robin pick highest-unclaimed from each bucket until `N` selected. |

**Bucketing rule** (used by `stratified_threshold_v1`):

```python
def bucket(metrics, thresholds: dict[str, tuple[int, int]]) -> Literal["high","medium","low"]:
    # thresholds[m] == (low_max, high_min)
    high_flags = [val >= thresholds[m][1] for m, val in metrics.items() if m in thresholds]
    low_flags  = [val <= thresholds[m][0] for m, val in metrics.items() if m in thresholds]
    if any(high_flags):  return "high"        # OR — inclusive: hard on either axis
    if all(low_flags):   return "low"         # AND — strict: trivial on both axes
    return "medium"
```

v1 ships `thresholds = {"cbo": (1, 5), "wmc": (5, 20)}` per Lanza & Marinescu (2006). The function shape generalizes to N metrics so RFC, LCOM4, or CC can be added in a future ADR amendment with one config change.

**Round-robin within stratified.** Per domain, classes within each bucket are sorted by composite score (descending), then by FQCN (ascending) as the deterministic tiebreaker. The selector picks `H[0], M[0], L[0], H[1], M[1], L[1], …` until `N` are chosen or all buckets are exhausted. If a bucket runs out mid-rotation, the rotation continues across the remaining buckets.

**Empty buckets.** When a domain has zero classes in a bucket (e.g., a pure-DTO domain with no "high" complexity), the missing bucket is recorded in `SelectionResult.empty_buckets[domain]` and an INFO log line emits a warning ("domain `users`: no 'low' complexity classes available — sampled 2/3"). The remaining slots are filled by continuing the rotation across the non-empty buckets.

**Per-domain default; global as opt-in.** `scope="per_domain"` (default) buckets and samples within each domain independently. `scope="global"` computes bucket boundaries from the whole corpus (so "high" means "high relative to all classes") but still samples per domain. The third potential meaning — global pool with no per-domain guarantee — is rejected because it would defeat the "every domain represented" property of the preview.

### Fork 3 — Domain definition: (e) hybrid (package-prefix default + manual override + LLM reported only)

```python
# codeograph/rendering/domain_grouping.py
from abc import ABC, abstractmethod

class DomainGrouping(ABC):
    @abstractmethod
    def assign(self, graph: CodeographKnowledgeGraph) -> dict[ClassId, str]:
        """Return class_id -> domain_name mapping."""


class PackagePrefixGrouping(DomainGrouping):
    """Default. First package segment below the longest common base prefix.

    Examples:
      com.example.users.controller.UserController     -> "users"
      com.example.users.service.UserService           -> "users"
      com.example.orders.checkout.OrderService        -> "orders"

    Edge cases:
      - Flat layout (all classes in base package): single domain named after the base.
      - Class outside the longest common prefix: assigned to "_unscoped" with warning.
    """


class ManualMappingGrouping(DomainGrouping):
    """Opt-in via codeograph.yaml. Pattern-to-domain rules; ant-style ** wildcard."""

    def __init__(self, rules: list[DomainMappingRule]) -> None: ...
```

```yaml
# codeograph.yaml — optional; default behavior needs no config
selection:
  cap: 3                                # CLI flag --max-classes-per-domain wins
  scope: per_domain                     # or "global"
  thresholds:                           # rare to override
    cbo: [1, 5]
    wmc: [5, 20]
  domain_grouping:
    strategy: package_prefix            # default; or "manual"
    manual_mapping:                     # used only if strategy: manual
      - pattern: "com.example.billing.**"
        domain: "payments"
      - pattern: "com.example.orders.**"
        domain: "payments"
```

**LLM-tagged grouping is reported, not selected.** The corpus-synthesis pass already produces a semantic domain view that can group across packages (e.g., `customer-management` spans `users` + `accounts`). That view is preserved in the scorecard as a *report* — "deterministic groups: `users, orders` / LLM-semantic groups: `customer-management, fulfillment` — 80% overlap" — but does NOT drive cap selection in v1. Driving selection from non-deterministic input would defeat the reproducibility property of the entire selector.

**Edge-case behaviors locked alongside:**
- Flat package layout (`com.example.UserController` with no sub-package): single domain named `"com.example"`; cap operates within it.
- Class outside the longest common prefix (defensive — should not happen in well-formed projects): synthetic `"_unscoped"` domain with an entry in `SelectionResult.empty_buckets["_unscoped"]` for the missing buckets and a WARN log line.
- A future `--report-semantic-domains` flag adds the LLM-tagged view to scorecards without changing selection.

### Fork 4 — Cap-exceeded behavior: (b) INFO log + summary table + manifest audit

The default cap binds on most real-world Spring Boot corpora (typical domains have 5–30 classes; default cap is 3). Cap binding is normal, not exceptional. Three logging touchpoints surface this without spamming:

**Start-of-run INFO line** prints the resolved cap value and the escape hatch:

```
[INFO] Rendering preview mode: --max-classes-per-domain=3 (default)
       Use --max-classes-per-domain 0 to render all classes.
```

**End-of-run summary table** is the single place a reader sees the full picture:

```
[INFO] Render summary:
       users     : 3 selected / 47 total  (strategy=stratified_threshold_v1)
       orders    : 3 / 28                 (strategy=stratified_threshold_v1)
       billing   : 2 / 2                  (strategy=take_all)
       shipping  : 3 / 5                  (strategy=top_n_v1)
[INFO] 11 of 82 classes rendered (13%). Details in ./out/manifest.json.
```

**Manifest is authoritative for machine consumers.** `SelectionResult` serializes into `manifest.json` so scorecards, future snapshot tests, and external CI parsers read structured data rather than parsing log lines.

WARN-per-domain (option c) is rejected because cap binding is the default behavior — emitting twenty WARN lines per typical run trains users to ignore the WARN channel and degrades the signal for genuinely exceptional events (empty buckets, future cost guardrails).

### Constraint flagged for ADR-016 (Cost-Control CLI, deferred to v1.1)

A `--strict-cap` flag — fail when the cap binds unless the user explicitly passed `--max-classes-per-domain` — is genuinely useful for production CI but belongs in the coherent cost-control CLI design (`--max-cost-usd`, `--dry-run`, `--strict-cap`) rather than being introduced one-off in v1.

### Constraint flagged for ADR-019 / ADR-021 (deferred to v1.1)

LLM-tagged domain grouping (Option c on Fork 3) can drive selection only when the snapshot-test layer and determinism contract land. Until then, the LLM view is reported alongside the deterministic view in scorecards but cannot be the selector's input.

### Constraint flagged for ADR-008

`ClassSelector` returns a `SelectionResult`; the pipeline subsets the graph to the selected class ids and passes the filtered subgraph to the renderer. The renderer signature (locked in ADR-008 Fork 1) does not need a `cap` parameter — selection is upstream of rendering.

### Constraint flagged for ADR-010

The per-class render granularity locked in ADR-010 Fork 8 multiplies neatly with per-class selection: every selected class is one cache key, one LLM call, one output file. The bucketing thresholds in this ADR ensure that the cached set covers the full difficulty spectrum so cache hit rates on subsequent runs reflect real corpus behavior, not over-representation of one complexity tier.

## Consequences

**Positive.**
1. The renderer stays focused on translation per ADR-008 Fork 5; selection logic does not duplicate across future renderers (Go, Rust, etc.).
2. `SelectionResult` is a pure transformation result, fully unit-testable without an LLM or filesystem.
3. The threshold-based bucketing reuses metrics already computed in the deterministic half of the pipeline (per ADR-004); no new metric extraction work.
4. The strategy ladder avoids paying stratification overhead on small domains where the cap does not meaningfully bind.
5. The cap value is changeable without re-running upstream stages — the graph and LLM annotations are cached; only selection and rendering re-run.
6. Scorecard readers see exactly which classes were selected and why, and which strategy fired per domain.

**Negative.**
1. Stratified sampling on the largest domains can produce a 1-1-1 representative slice that omits a project's most-important class if that class is in a bucket that happens to be over-represented in selection rounds — the design choice favors *coverage of difficulty* over *picking the headline class*.
2. Empty-bucket warnings will fire on real corpora (pure-DTO domains, anemic packages) and may be perceived as noise even though they are honest information; users can suppress with log level if desired.
3. The default cap of 3 leaves no headroom for "best-of-bucket" picking when stratification fires — at `n ≥ 6` (the strategy-ladder threshold for stratification), exactly one class per bucket is selected. Users wanting richer samples increase the cap.
4. Package-prefix grouping is fooled by layouts that put the domain two segments deep (`com.org.product.users.controller.X` groups as `product`, not `users`); the `manual_mapping` override exists to fix this but requires user config.
5. Logging two touchpoints (start INFO and end summary) plus the manifest field means three places to maintain when the audit fields evolve.

## Confirmation

1. Running `ClassSelector(cap=3).select(graph, annotations)` on a corpus with domains `users(47)`, `orders(28)`, `billing(2)` produces `selected["users"]` of length 3, `selected["orders"]` of length 3, `selected["billing"]` of length 2 (verified by unit test).
2. The same call returns `strategy_per_domain == {"users": "stratified_threshold_v1", "orders": "stratified_threshold_v1", "billing": "take_all"}` (verified by unit test).
3. Running the same selection twice on the same input produces equal `SelectionResult` objects — including identical class id ordering within each domain's `selected` list (verified by unit test asserting equality).
4. A domain with all classes in the "high" bucket produces `SelectionResult.empty_buckets[domain] == ["medium", "low"]` and an INFO log warning for each (verified by unit test asserting the entry plus a log-capture fixture).
5. Running on a project with package layout `com.org.product.users.X` produces `PackagePrefixGrouping().assign(graph)` mapping every class to the `"product"` domain by default; supplying `ManualMappingGrouping` with `pattern: "com.org.product.users.**" -> domain: "users"` overrides to the `"users"` domain (verified by two unit tests).
6. `bucket({"cbo": 8, "wmc": 3}, thresholds={"cbo":(1,5),"wmc":(5,20)})` returns `"high"` (OR rule); `bucket({"cbo": 1, "wmc": 4}, ...)` returns `"low"` (AND rule); `bucket({"cbo": 3, "wmc": 10}, ...)` returns `"medium"` (verified by parameterized unit test).
7. The CLI command `codeograph run ./fixture --out ./out` prints the start-of-run preview-mode INFO line (matching the exact format above) and the end-of-run summary table (one row per domain, plus the total ratio line); both lines are captured by a CLI integration test.
8. The `manifest.json` produced by a run contains a `selection` field whose schema matches `SelectionResult` (verified by a JSON-schema validation test).
9. Passing `--max-classes-per-domain 0` disables the cap entirely; all classes in every domain are selected; `strategy_per_domain` records `"take_all"` for every domain (verified by integration test).
10. Mypy/pyright accept a concrete `DomainGrouping` subclass whose `assign()` method returns `dict[ClassId, str]`; reject a subclass returning `dict[str, ClassId]` or `list[ClassId]` (verified by a type-error fixture).

## Pros and Cons of the Considered Options

### Fork 1+2 — Selection placement

**(a) pipeline-layer `ClassSelector` component. ✅ Chosen.**
* Good, because selection logic is one class with one job — renderer stays focused on translation.
* Good, because the component is purely deterministic; tested without LLM mocks or filesystem fixtures.
* Good, because the `SelectionResult` artefact gives scorecards and the future eval framework a structured audit they read directly.
* Good, because the same component serves every future target language — no per-renderer reimplementation.
* Bad, because it adds one new component to the pipeline (plus a `DomainGrouping` ABC and at least two concrete groupings).
* Neutral, because the graph "subset" operation must be defined carefully — calls to skipped classes are kept as `unresolved_call` edges so the renderer's error-handling still sees them.

**(b) renderer-layer cap parameter.**
* Good, because no new pipeline component.
* Bad, because it violates the renderer contract from ADR-008 Fork 5 — renderer's job is "translate what I am given," not filter.
* Bad, because every future renderer must reimplement the same selection logic.
* Bad, because manifest recording becomes renderer-specific — loses the unified audit story.

**(c) graph-annotation layer (`render_selected: bool` on nodes).**
* Good, because selection becomes a graph property visible to any downstream tool.
* Bad, because it pollutes the graph schema with rendering-stage concerns; the graph captures structure, not cost-discipline knobs.
* Bad, because changing the cap requires rebuilding the graph artefact — defeats the caching property.
* Bad, because if an LLM pass performs the selection, the selection becomes non-deterministic, contradicting FR-14.

**(d) inline in CLI.**
* Good, because zero new components.
* Bad, because logic ends up in the CLI handler — the god-script anti-pattern.
* Bad, because the selection cannot be reused from a programmatic Python entry point.
* Bad, because the logic is harder to unit-test when embedded in a Click command.

### Fork 1+2 — Sampling strategy

**(α) quantile-based (top/middle/bottom third).**
* Good, because it auto-adjusts to corpus distribution.
* Bad, because "middle" is a fake midpoint on bimodal corpora — wastes a slot on a low-density region.
* Bad, because "low" often selects DTOs or anemic entities — a wasted preview slot.
* Bad, because the bucket boundaries are corpus-relative, so the labels are not comparable across runs of different corpora.

**(β) pure threshold bucketing (`N/3` from each bucket).**
* Good, because thresholds are absolute (cited from Lanza & Marinescu 2006), so labels are comparable across corpora.
* Good, because the bucketing reuses metrics ADR-004 already produces.
* Bad, because uneven bucket sizes need a spillover policy that the simple "`N/3` from each" formula does not specify.
* Bad, because within-bucket ordering is undefined without an explicit tiebreaker.

**(γ) bucket + rank-within-bucket + tiered strategy ladder. ✅ Chosen.**
* Good, because it is explicitly representative (preserves the preview purpose) AND picks the best-of-bucket within each tier (preserves the "show interesting classes" property).
* Good, because the strategy ladder avoids stratification overhead when the domain is too small to bucket meaningfully.
* Good, because the named strategy (`take_all`, `top_n_v1`, `stratified_threshold_v1`) per domain self-documents in `SelectionResult` and in the end-of-run summary.
* Good, because empty buckets degrade gracefully — rotation continues across remaining buckets without an extra branching policy.
* Bad, because it is the most complex of the three strategies in terms of code and tests.
* Bad, because the default cap of 3 leaves no headroom for picking multiple representatives per bucket when stratification fires.

### Fork 3 — Domain definition

**(a) Maven module name.**
* Good, because it is explicit, structural, and available at Pass 0 with no LLM cost.
* Bad, because monolithic single-module projects collapse to a single domain — the cap becomes useless.
* Bad, because module names often reflect *layer* (`web`, `core`, `commons`) rather than *domain*.
* Bad, because Gradle and ad-hoc layouts are excluded.

**(b) package-prefix heuristic.**
* Good, because it is deterministic from AST alone.
* Good, because it matches the convention most Spring Boot teams already follow.
* Bad, because deeply nested layouts (`com.org.product.users.controller.X`) group incorrectly without an override.
* Bad, because cross-package semantic domains cannot be expressed.

**(c) LLM-tagged from Pass 2.**
* Good, because the domain labels match how an engineer describes the system.
* Good, because the synthesis pass already produces them — zero additional work.
* Bad, because the labels are non-deterministic on cache misses — defeats FR-14.
* Bad, because selection becomes dependent on Pass 2 having run, so `--ast-only` mode breaks.

**(d) explicit user-provided mapping.**
* Good, because the user expresses their own taxonomy precisely.
* Bad, because it requires user setup before any output is produced — kills the zero-config promise.
* Bad, because the pattern syntax is a learning curve and validation (complete, non-overlapping) is non-trivial.

**(e) hybrid — (b) default, (d) opt-in override, (c) reported only. ✅ Chosen.**
* Good, because it works zero-config on the realistic majority of Spring Boot projects.
* Good, because the override path covers the layouts where (b) fails without forcing every user to write config.
* Good, because all selection paths stay fully deterministic per FR-14.
* Good, because the LLM-semantic view remains available as a *reporting* signal alongside the deterministic groups — useful eval content without coupling selection to non-deterministic input.
* Bad, because two code paths must be maintained, though each is independent and small.

### Fork 4 — Cap-exceeded behavior

**(a) silent truncation.**
* Good, because zero log noise.
* Good, because the manifest still carries the full audit.
* Bad, because the user gets a 3-class output and may not realize a cap was applied.
* Bad, because CI builds "pass" without anyone noticing the preview was tiny.

**(b) INFO at start + end-of-run summary + manifest. ✅ Chosen.**
* Good, because the user sees they are in preview mode at run start with the concrete flag value and escape hatch printed.
* Good, because the end-of-run summary table makes "you did not render everything" impossible to miss.
* Good, because the aggregate ratio framing (`14/94 = 15%`) is the right shape for scorecard readers.
* Good, because it does not spam WARN per domain — fits the reality that cap-binds-is-normal.
* Bad, because two log points must stay in sync with the underlying `SelectionResult` shape.

**(c) WARN per domain.**
* Good, because it is maximally loud.
* Bad, because it spams a 20-domain project with 20 WARN lines on every run.
* Bad, because it trains users to ignore the WARN channel, degrading the signal for genuinely exceptional events.
* Bad, because it treats normal behavior as exceptional.

**(d) (b) plus `--strict-cap`.**
* Good, because it adds a production CI guardrail without changing default UX.
* Bad, because it introduces a one-off CLI flag in v1 ahead of the coherent cost-control CLI design.
* Neutral, because the natural home for the flag is the future cost-control CLI ADR.

**(e) (b) plus `RENDERED.md`.**
* Good, because the recipient of the output (not just the runner) sees the preview signal.
* Bad, because it adds a non-source-code file to renderer output — mild scope creep.
* Bad, because the artefact's ownership (pipeline vs renderer) requires an additional design call.

## More Information

### Relationships

* **ADR-002** (input-agnostic design) — `PackagePrefixGrouping` works on every Java project regardless of build tool; the Maven-module-as-domain option (rejected) would have inherited ADR-002's Maven-only limitation.
* **ADR-003** (parsing strategy) — `unresolved_call` edges to skipped classes are preserved on the filtered subgraph so the renderer's edge-handling logic still sees them.
* **ADR-004** (complexity model) — the `CBO` and `WMC` metrics this ADR uses for bucketing are emitted in their raw form per ADR-004 TP-d; no `migration_difficulty` tag is consumed. This ADR is one of the downstream consumers ADR-004 §201 forward-referenced.
* **ADR-006** (knowledge graph schema) — `SelectionResult` is a rendering-layer concept and does NOT mutate the graph schema; the selected/skipped sets are filtering metadata, not graph nodes.
* **ADR-008** (pluggable renderer interface) — the pipeline subsets the graph by `selected` before invoking `renderer.render()`; the renderer signature stays unchanged.
* **ADR-010** (Spring → TS/NestJS mapping) — per-class render granularity means one selected class is one cache key and one LLM call; bucketing ensures the cached set covers the full difficulty spectrum.
* **ADR-013** (LLM provider abstraction) — selection runs without invoking the provider; `--ast-only` mode produces a meaningful `SelectionResult` even when no LLM pass has run.
* **ADR-015** (telemetry + response cache) — the `SelectionResult.selected` class set determines which classes the renderer asks the cache about; the bucketing ensures cache hit rates over time reflect real difficulty distribution rather than skewed top-N caching.

### Deferred items

* **`--strict-cap` flag** — moved to the future Cost-Control CLI ADR, alongside `--max-cost-usd` and `--dry-run`, as a coherent CI hardening set.
* **LLM-tagged domain grouping driving selection** — triggered when the future Snapshot Tests ADR and Determinism Contract ADR land; the reporting-only path remains in v1 as the bridge.
* **Additional metrics in bucketing (RFC, LCOM4, CC)** — the `thresholds` dict shape already supports them; adding any requires this ADR's threshold table to cite the threshold sources.
* **`RENDERED.md` summary file in output directory** — added only if real users report being surprised by a preview being mistaken for a full run.
* **Annotation-diversity tiebreaker within buckets** — could prefer classes that touch more distinct Spring annotations as a coverage signal; deferred until the simpler composite ordering proves insufficient.
* **`scope="global"` semantics other than "global thresholds + per-domain sampling"** — explicitly rejected the third meaning ("global pool, no per-domain guarantee") because it would defeat the every-domain-represented property.

### Open Questions / Future Work

* Did the `stratified_threshold_v1` strategy fire frequently enough to justify its complexity, or did most domains land in `take_all` or `top_n_v1`? Review after the first multi-corpus run.
* Did OR-high / AND-low bucketing produce well-balanced buckets in practice, or did one bucket dominate on real corpora?
* Did any users provide `manual_mapping` configs, or did `PackagePrefixGrouping` suffice for every encountered project?
* Did the `empty_buckets` warning surface usefully, or did it become noise users learned to filter out?
* Did the end-of-run summary table actually prevent the "user surprised by 3-class output" failure mode?

### References

* Lanza, M., & Marinescu, R. (2006). *Object-Oriented Metrics in Practice: Using Software Metrics to Characterize, Evaluate, and Improve the Design of Object-Oriented Systems.* Springer. — source for the CBO ≥ 5 and WMC ≥ 20 thresholds used in bucketing.
* MADR template — https://github.com/adr/madr
