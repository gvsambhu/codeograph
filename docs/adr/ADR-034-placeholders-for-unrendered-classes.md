---
status: proposed
date: 2026-11-01
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-034 — Placeholders for Unrendered Classes

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `420f2b5` (2026-11-01). ADR text is
cited as it stands at that commit.

A class selected for rendering can end up with no output for two reasons, and both are decided as
omission:

| Case | Decided by | What the output holds |
|---|---|---|
| The class's render call fails after retries | ADR-008's 2026-06-21 amendment, decision D-008-2: *"omits that class's file, records it in the run manifest, and continues"* — a placeholder was rejected because it *"ships non-compiling output"* | Nothing |
| The class is refused by policy — a security feature under `security_feature_policy=refuse`, reactive code under `webflux_policy=refuse`, an out-of-scope framework | ADR-010 Fork 9: refused classes *"move from `selected` to `refused`"* and are not rendered | Nothing |

**The requirements ask for the opposite.** FR-36 is a negative guarantee — *"No source feature is ever
silently dropped from rendered source"* — and its AC-1 requires that *"an untranslatable feature surfaces
as a reviewable placeholder carrying the original intent"*. AC-2 requires that security-relevant features
default to refusal *"so a rendered endpoint is never silently less protected than its source"*. FR-3 AC-2
requires that each source class map to an identifiable unit of the output. An omitted class satisfies none
of these: a reviewer reading the rendered project cannot see that it is missing, and code that imports it
fails to compile.

**D-008-2's objection was sound for the placeholder it considered** — free text, which does not compile.
It does not hold for a placeholder generated with the class's real shape.

**This ADR decides what a selected class that is not rendered leaves in the output.** It supersedes
ADR-008's D-008-2 and ADR-010 Fork 9's refuse-means-no-file behaviour. The refusal policies themselves —
which features are refused, and their defaults and presets — are unchanged, and the record of each refusal
and failure stays in the render audit (ADR-029; the output-layout amendment to ADR-010).

## Decision Drivers

* **No silent failures** — a class that is not rendered is visible in the rendered project itself, not only
  in a record beside it (FR-36).
* **Never less protected than the source** — a placeholder exposes nothing the source protected (FR-36
  AC-2).
* **Determinism / determinism boundary clarity** — the placeholder is a function of the graph, so the
  failure case does not depend on the component that failed.
* **The rendered project still compiles and starts** — dependents of an unrendered class keep working
  (FR-3 AC-1).
* **Tractable v1 implementation** — one generator per target, from data the renderer already has.

## Considered Options

### Fork 1 — What an unrendered class leaves in the output

* (a) Nothing; the omission is recorded beside the output (D-008-2, ADR-010 Fork 9).
* **(b) A typed skeleton of the class, in the file it would have had. ✅**
* (c) A comment-only file naming the class and the reason.
* (d) Abort the whole render.

### Fork 2 — How the skeleton is produced

* (a) By the LLM, with a skeleton prompt.
* **(b) Deterministically from the graph, by the renderer. ✅**

### Fork 3 — What the skeleton registers with the framework

* (a) Everything the rendered class would have registered.
* (b) Nothing.
* **(c) Dependency-injection registration only — never routes, handlers or security decorators. ✅**

## Decision Outcome

### Fork 1 — A typed skeleton: (b)

For every selected class that is refused or whose render call fails, the output contains a **skeleton**
at the path the rendered class would have had:

* the class, under its mapped name, with its fields and method signatures in the target's types (ADR-010's
  type mapping);
* **a type the mapping does not translate** — a reactive `Mono`/`Flux` under `webflux_policy=refuse`, an
  out-of-scope framework's type — becomes the target's top type (for TypeScript, `unknown`), with a TODO
  naming the source type, so the skeleton compiles without inventing a translation;
* **per kind:** a class's method bodies throw a not-rendered error; an interface carries its method
  signatures only; an enum carries its constants; a record carries its components as read-only fields; an
  abstract class keeps its abstract methods abstract; a nested class is generated where the target's
  mapping places it;
* a header comment stating that the class was not rendered, why — the refusing policy and the feature it
  matched, or the fixed reason *render call failed after retries* — and the original class's fully
  qualified name and corpus-relative source path, so a reviewer has the original intent and knows where to
  start (FR-36 AC-1). **The header never carries a provider's error text**, which varies between attempts;
  that detail goes to the render audit and the log.

The render audit records each placeholder with its reason and, for a failure, the error detail (alongside
the refusals and failures it already holds). The compile check covers placeholders like any other file.

**The render's outcome** follows ADR-031: a placeholder written because a render call failed makes the
render *completed with recorded failures* (status 2); a placeholder written because a policy refused the
class is the policy working as configured, not a failure.

### Fork 2 — Generated from the graph: (b)

The skeleton is built from the class's graph node and the target's type mapping — no LLM call. It is
therefore byte-stable for a fixed graph (FR-23), cheap, and available precisely when the LLM is what
failed. Each renderer supplies its own generator; the renderer interface gains it (see *Constraints
flagged*).

### Fork 3 — Injection registration only: (c)

* **Kept:** the class's dependency-injection registration (for TypeScript/NestJS, `@Injectable()` and its
  module's provider entry), so dependents still resolve their constructor dependencies and the project
  starts (FR-3 AC-1).
* **Never emitted:** route and handler registration (controller and method-mapping decorators), and any
  security-relevant decorator. A refused controller therefore exposes no endpoint at all — less
  functional than the source, never less protected (FR-36 AC-2). A call into a skeleton method fails
  closed, with the not-rendered error.

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-008
The renderer interface gains a placeholder generator — given a class node and a reason, it returns the
skeleton's path and content. Every renderer implements it (NFR-5: adding a render target changes no shared code).
On acceptance, D-008-2 carries a *superseded by ADR-034* note.

#### Constraint flagged for ADR-010
The TypeScript/NestJS renderer implements the generator under Fork 3's registration rule and Fork 1's
type fallback; on acceptance, Fork 9's refuse behaviour carries a *superseded by ADR-034* note. The
policies and presets are unchanged. **Open for ADR-010:** a refused *cross-cutting* security class — a
`SecurityFilterChain` configuration, a security filter — protected other controllers in the source. Its
skeleton exposes nothing, but the controllers it protected still render, without that protection. This
ADR does not close that case; FR-36 AC-2 needs ADR-010 to decide it.

#### Constraint flagged for the render audit's contents
The output-layout amendment to ADR-010: each placeholder is listed with its reason, and each failure with
its error detail.

#### Constraint flagged for ADR-032
Features in refused classes **and in classes whose render call failed** count as not emitted, because a
skeleton translates none of them.

## Consequences

* Good, because every selected class is visible in the rendered project, with its reason and its origin.
* Good, because code that depends on an unrendered class still compiles and wires, so one failed class no
  longer breaks its dependents.
* Good, because a refused controller exposes nothing, so a refused class's own endpoints can never be less
  protected than in the source.
* Bad, because a refused cross-cutting security class leaves the controllers it protected rendered without
  that protection — a gap this ADR records for ADR-010, not one it closes.
* Good, because the placeholder is deterministic and costs no LLM call.
* Bad, because the rendered project contains classes that throw when called — a dependent's runtime path
  through one fails, which is the honest outcome for an unrendered dependency.
* Bad, because each renderer must implement a skeleton generator.
* Neutral, because the render audit gains a placeholder list.

## Confirmation

1. A class whose render call fails after retries yields a skeleton at its mapped path, with every method
   signature in the target's types and a header giving the fixed reason, the original fully qualified name
   and the source path — and no provider error text, which the render audit carries instead (integration
   test with a failing mock provider).
2. A controller refused under `security_feature_policy=refuse` yields a skeleton with no route, handler or
   security decorator, and the rendered app exposes no route for it (integration test asserting the
   registered routes).
3. A service that a rendered class injects, and that is itself refused, yields a skeleton with its
   injection registration; the rendered project compiles and starts (integration test running the compile
   check and a boot smoke test).
4. Calling any skeleton method raises the not-rendered error (unit test on a generated skeleton).
5. Two renders of the same graph with the same refusals, and two renders in which the same class's call
   fails with different provider errors, produce byte-identical skeletons (unit tests).
6. The render audit lists each placeholder with its reason, and each failure with its error detail
   (integration test).
7. No skeleton is produced for a class that was not selected; the cap is unaffected (unit test).
8. A WebFlux class refused under the default policy yields a skeleton whose `Mono`/`Flux` types are the
   target's top type with a TODO naming each source type, and it compiles (integration test).
9. A refused interface, enum and record each yield a skeleton of their kind — signatures only, constants,
   read-only fields — and compile (unit tests).
10. A render with one failed class exits with status 2; a render whose only placeholders are policy
    refusals exits with 0 (integration tests).

## Pros and Cons of the Considered Options

### Fork 1 — What an unrendered class leaves in the output

**(a) Nothing, recorded beside the output.**
* Good, because no unfinished code ships.
* Good, because it needs no generator.
* Bad, because the rendered project hides the gap, dependents fail to compile, and FR-36 AC-1 is unmet.

**(b) A typed skeleton. ✅ Chosen.**
* Good, because the gap is visible where the reviewer works, with the original intent.
* Good, because dependents compile and wire, answering D-008-2's objection.
* Bad, because the project contains code that throws when reached.

**(c) A comment-only file.**
* Good, because the gap is visible.
* Good, because it is trivial to produce.
* Bad, because dependents' imports fail to compile.

**(d) Abort the render.**
* Good, because nothing partial ships.
* Good, because it is simple.
* Bad, because one class discards every other class's output (D-008-2 rejected it for that reason).

### Fork 2 — How the skeleton is produced

**(a) By the LLM.**
* Good, because the skeleton could carry richer hints.
* Good, because it reuses the render path.
* Bad, because it is non-deterministic and unavailable in exactly the case where the LLM failed.

**(b) From the graph. ✅ Chosen.**
* Good, because it is deterministic and costs no call.
* Good, because it works whatever failed.
* Bad, because each renderer needs its own generator.

### Fork 3 — What the skeleton registers

**(a) Everything the rendered class would have.**
* Good, because the app's wiring is complete.
* Good, because the skeleton mirrors the intended class most closely.
* Bad, because a refused controller would expose routes with no protection — exactly what FR-36 AC-2
  forbids.

**(b) Nothing.**
* Good, because nothing is exposed.
* Good, because it is simplest.
* Bad, because dependents that inject the class fail at startup.

**(c) Injection registration only. ✅ Chosen.**
* Good, because dependents wire and the project starts.
* Good, because no route, handler or security surface is exposed.
* Bad, because the generator must know which decorators are injection and which are routing, per target.

## More Information

### Relationships

* **ADR-008** (pluggable renderer interface) — this ADR supersedes D-008-2 and adds the placeholder
  generator to the interface.
* **ADR-010** (Spring → TypeScript/NestJS mapping) — this ADR supersedes Fork 9's refuse-means-no-file
  behaviour; the policies, defaults and presets stand.
* **ADR-009** (rendering budget cap) — only selected classes get placeholders.
* **ADR-029** (output layout and ownership) — the render audit's location.
* **ADR-031** (command outcomes and consent) — a failure placeholder makes the render status 2.
* **ADR-032** (evaluation check semantics) — `coverage` reads the render audit and counts refused and
  failed classes as not emitted.

### Requirements touched

FR-3 AC-1, AC-2 · FR-23 · FR-36 AC-1, AC-2 · FR-45 AC-1 · NFR-5 AC-1.

### References

* Requirements — `docs/requirements.md` (FR-3, FR-36).
* NestJS documentation, *Providers* — https://docs.nestjs.com/providers

### Deferred

* The Go renderer's generator — with the Go renderer (ADR-011, v1.1).

## Revision history

* **2026-11-10** — NFR-5 cited by its reworded AC-1 (adding a render target changes no shared code) instead of the removed wording. Reference fix; no decision changed.
