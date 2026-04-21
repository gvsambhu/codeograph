---
status: "accepted"
date: 2026-04-21
decision-makers: Ganesh
consulted: —
informed: —
---

# ADR-004 — Complexity Model: Metrics, Computation, and Reference Thresholds

## Context and Problem Statement

Stage 2 of the pipeline produces a graph whose nodes (classes, methods) carry complexity attributes. Four downstream consumers will read those attributes:

* **LLM migration-hazard prompting** — high-complexity methods need extra warning context.
* **Eval weighting (ADR-017)** — eval scores should weight by node complexity.
* **Token strategy (ADR-005)** — method size determines whether one prompt suffices or chunking is needed.
* **Class selection under `--max-classes-per-domain` (ADR-009)** — when only N of M classes can be rendered, complexity informs which ones.

ADR-003 committed the AST layer as the locus of complexity computation and pinned the *minimum* metric set as cyclomatic + cognitive. This ADR pins the full v1 metric set, the canonical computation method for each, the citations behind every reference value, and the policy for how downstream consumers pick their own thresholds.

A project guardrail applies: every threshold cited in this ADR must reference a published source (paper or rule documentation). No values picked from memory.

## Decision Drivers

* **Citation discipline.** Every number in this ADR must trace to a published source.
* **Consumer flexibility.** Different consumers want different cuts on the same raw value (binary flag for token strategy, sort key for class selection, weight curve for eval). Forcing all consumers through one tier vocabulary creates either over-specification or wasted attributes.
* **Schema simplicity.** The knowledge graph schema (ADR-006) shouldn't carry derived labels nobody queries.
* **Extensibility.** Adding metrics later (DIT, RFC, custom) should be additive — new key in the complexity dict, no schema or downstream-ADR revisions.
* **Determinism.** All metrics must be reproducibly computed from AST input alone (no LLM judgment, no heuristic randomness).

## Considered Options

**Metric set for v1**
* MS1 — minimum (cyclomatic + cognitive only, ADR-003's floor)
* MS2 — high-signal six (cyclomatic, cognitive, WMC, CBO, LCOM4, method LoC)  *(chosen)*
* MS3 — full CK suite + size + cognitive (adds DIT, RFC, NOC)

**Threshold policy**
* TP-a — three tiers per metric, labels in graph (`*_tier: low|medium|high`)
* TP-b — single binary cut per metric, flag in graph (`*_elevated: bool`)
* TP-c — three tiers with explicit overrides where Codeograph deviates from cited sources
* TP-d — raw numbers only in the graph; ADR-004 publishes a cited reference table; each downstream ADR picks and cites its own cut  *(chosen)*

## Decision Outcome

### 1. v1 metric set (MS2)

Six metrics, all computed by the AST layer, all emitted as integers in the per-method or per-class `complexity` dict. Two are method-level, three are class-level, one (WMC) aggregates method-level into class-level.

| # | Metric | Scope | Source of definition |
|---|---|---|---|
| 1 | Cyclomatic Complexity (CC) | per method | McCabe (1976) |
| 2 | Cognitive Complexity | per method | Campbell / SonarSource (2018) |
| 3 | Weighted Methods per Class (WMC) | per class | Chidamber & Kemerer (1994) |
| 4 | Coupling Between Object classes (CBO) | per class | Chidamber & Kemerer (1994) |
| 5 | Lack of Cohesion of Methods (LCOM4) | per class | Hitz & Montazeri (1995) |
| 6 | Method Lines of Code | per method | SonarSource `java:S138` |

**Deferred to a later ADR (or revision of this one):**
* DIT (Depth of Inheritance Tree) — low signal for typical Spring Boot user code.
* RFC (Response For a Class) — overlaps CBO without distinct signal.
* NOC (Number of Children) — research metric; downstream consumers identified no use.

### 2. Threshold policy (TP-d) — raw numbers only

The graph carries raw integer values per metric. **No tier labels, no binary flags** are stored on graph nodes by this ADR.

ADR-004 publishes the **Reference Threshold Table** (below) — a cited compendium of standard cuts from the original sources. Each downstream ADR (ADR-005, ADR-009, ADR-017, renderer prompt templates) picks the cut appropriate to its use case from this table and cites it in its own ADR text.

The guardrail "every threshold cites its source" is satisfied: ADR-004 supplies the citation library; downstream ADRs cite from it whenever they apply a cut.

If a future consumer pattern emerges that benefits from standardised tier labels in the graph, this ADR can be revised to TP-a (additive change — adds keys to the complexity dict; existing consumers unaffected).

### 3. Computation specifications (canonical, deterministic)

Each metric below is implemented in the AST walker exactly as specified. Specifications are normative for v1.

#### 3.1 Cyclomatic Complexity (CC)
* Per method.
* Counted as 1 + the number of branching constructs in the method body, where branching constructs are: `if`, `else if`, `case`, `for`, `while`, `do-while`, `catch`, ternary `?:`, `&&`, `||`.
* `switch` arms count once per `case` label (each `case` is a branch); `default` does not add to count.
* Lambda bodies are computed independently as nested methods (their CC does not roll up to the enclosing method).
* Source: McCabe, T.J. (1976). "A Complexity Measure." *IEEE Transactions on Software Engineering*, 2(4), 308–320.

#### 3.2 Cognitive Complexity
* Per method.
* Computed per the SonarSource specification: each control-flow break adds a base score; nesting adds an increment proportional to current nesting depth; sequences of logical operators add 1 each; recursion adds 1.
* Reference implementation algorithm: Campbell, G.A. (2018). "Cognitive Complexity: A new way of measuring understandability." SonarSource. https://www.sonarsource.com/docs/CognitiveComplexity.pdf

#### 3.3 Weighted Methods per Class (WMC)
* Per class.
* Sum of CC across all methods declared in the class (including constructors; excluding inherited methods).
* Synthetic Lombok-generated methods (ADR-003 §6) contribute CC = 1 each.
* Source: Chidamber, S.R. & Kemerer, C.F. (1994). "A Metrics Suite for Object Oriented Design." *IEEE Transactions on Software Engineering*, 20(6), 476–493.

#### 3.4 Coupling Between Object classes (CBO)
* Per class.
* Count of distinct other classes referenced by this class via: field types, parameter types, return types, locally-declared variable types, throws clauses, and resolved call targets (`resolved_call` edges from ADR-003).
* JDK classes are excluded (rationale: every class implicitly references `Object`, `String`, etc.; including these inflates CBO uniformly and adds no signal).
* Self-references are excluded.
* `unresolved_call` targets are excluded (no class identity to count).
* Source: Chidamber & Kemerer (1994), op. cit.

#### 3.5 Lack of Cohesion of Methods (LCOM4)
* Per class.
* Build the undirected graph G over all methods of the class, where an edge connects two methods if they access at least one field in common, *or* one method calls the other directly.
* LCOM4 = number of connected components in G. LCOM4 = 1 ⇒ fully cohesive class.
* Constructors and Lombok-synthesised accessors are included as nodes.
* Source: Hitz, M. & Montazeri, B. (1995). "Measuring Coupling and Cohesion In Object-Oriented Systems." *Proc. Int. Symp. Applied Corporate Computing*. (LCOM4 introduced as a connected-components reformulation correcting CK94's original LCOM.)

#### 3.6 Method Lines of Code
* Per method.
* Physical lines of code in the method body (opening brace line through closing brace line, inclusive).
* Blank lines and comment-only lines are *included* (matches SonarSource convention).
* Synthetic Lombok-generated methods report LoC = 0.
* Source: SonarSource rule `java:S138` ("Methods should not have too many lines"). https://rules.sonarsource.com/java/RSPEC-138/

### 4. Reference Threshold Table (cited; for downstream consumer use)

> Downstream ADRs cite this table when applying a cut. ADR-004 itself does not apply any of these cuts — it documents them.

| Metric | Cut value | Meaning | Source |
|---|---|---|---|
| CC | 10 | upper bound for "well-structured" | McCabe (1976); confirmed NIST SP 500-235 (Watson & McCabe, 1996) §2.5; also SonarSource `java:S1541` default |
| CC | 20 | medium → high boundary | McCabe (1976) |
| CC | 50 | "untestable" | McCabe (1976) |
| Cognitive | 15 | rule default warning | SonarSource `java:S3776` |
| WMC | 20 | low → average boundary | Lanza, M. & Marinescu, R. (2006). *Object-Oriented Metrics in Practice*. Springer. |
| WMC | 100 | average → very high boundary | Lanza & Marinescu (2006) |
| CBO | 5 | low → high boundary | Lanza & Marinescu (2006) |
| CBO | 9 | high → very high boundary | Lanza & Marinescu (2006) |
| CBO | 14 | fault-proneness threshold (validation study) | Basili, Briand & Melo (1996), "A Validation of OO Design Metrics as Quality Indicators." *IEEE TSE* 22(10) |
| LCOM4 | 1 | cohesion target (any value > 1 indicates split candidate) | Hitz & Montazeri (1995) |
| Method LoC | 100 | rule default warning | SonarSource `java:S138` |
| Method LoC | 20 | conservative refactor target | Martin, R.C. (2008). *Clean Code*, ch. 3 |

### Consequences

* Good, because every metric and every reference value in this ADR has a published source — guardrail satisfied.
* Good, because the graph schema (ADR-006) only grows by one numeric field per metric — no derived label vocabulary to maintain.
* Good, because adding metrics later is purely additive: new key in the complexity dict, no schema revision, no downstream-ADR revision.
* Good, because each downstream consumer's threshold is justified at the point of use, in the ADR closest to its consequences.
* Bad, because no consistent cross-cutting "complex" label exists in the graph — eval dashboards or third-party tooling that wants a categorical attribute must compute it from raw values.
* Bad, because if multiple consumers independently pick the same cut, the citation appears in multiple ADRs (mild duplication, accepted in exchange for consumer-local clarity).
* Bad, because thresholds for v1 are scattered across consumer ADRs rather than centralised; reviewing "all thresholds in use" requires walking the consuming ADRs.

### Confirmation

* **Unit:** per-metric computation tests against curated fixtures with hand-verified expected values (a method whose CC the developer counted manually; a class whose LCOM4 components the developer drew on paper).
* **Reference cross-check:** at least one fixture per metric whose value matches the corresponding rule's published expected output (e.g. SonarSource example for cognitive complexity has known-value sample code).
* **Lombok-synth coverage:** fixture asserting WMC includes synthesised Lombok accessors at CC = 1, and method LoC = 0 for them.
* **Determinism:** running the AST walker twice on identical input produces byte-identical complexity output.

## Pros and Cons of the Options

### Metric set

**MS1 — minimum only**
* Good, because smallest implementation surface.
* Bad, because three of the four downstream consumers (eval weighting, class selection, domain split signal) get no useful input from CC + cognitive alone.

**MS2 — high-signal six** *(chosen)*
* Good, because covers all four downstream use cases identified in Decision Drivers.
* Good, because every metric has a published source and a non-trivial signal beyond what CC alone provides.
* Bad, because more AST walker code to write and test (manageable; each is one tree walk).

**MS3 — full CK suite plus**
* Good, because most-defensible "we computed everything standard."
* Bad, because DIT, RFC, NOC have no identified consumer in v1; carrying unused metrics inflates the graph and the test surface for no benefit.

### Threshold policy

**TP-a — three tiers, labels in graph**
* Good, because dashboards and queries can filter by tier directly.
* Bad, because ~18 boundaries pinned in this ADR; tier labels travel with every node whether queried or not.
* Bad, because a single tier vocabulary forces downstream consumers to fit their use case to it (binary needs, sort needs, weighting needs all squeezed through one shape).

**TP-b — single binary cut, flag in graph**
* Good, because minimal graph surface.
* Bad, because the single cut isn't right for every consumer (eval weighting wants raw, class selection wants sort).

**TP-c — three tiers with overrides**
* Good, because expressive when standard tiers don't fit Codeograph's needs.
* Bad, because highest editorial load (full tier table + overrides table); same shape as TP-a in the graph, so adds work without adding flexibility.

**TP-d — raw numbers + reference table** *(chosen)*
* Good, because the graph carries truth (raw integers); derived categorisations live where they're consumed.
* Good, because ADR-004 stays a reference document — adding metrics or revising one cut doesn't ripple through the schema.
* Good, because downstream ADRs cite from a single library — no scattered "I picked 12 because it felt right" reasoning.
* Bad, because no graph-level "complex" label; tooling that wants one must compute it.
* Bad, because thresholds are spread across consuming ADRs; reading "all live thresholds" requires walking those ADRs.
* Future-compatible with TP-a if a tier label proves needed (additive — adds dict keys, doesn't break existing consumers).

## More Information

**Relationship to ADR-003.** ADR-003 reserved the AST layer as the complexity-computation locus and pinned the minimum (CC + cognitive). ADR-004 extends the pinned set to six metrics. The AST-stage `MethodFact.complexity` and `ClassFacts.complexity` dicts (ADR-003 §7) gain the new keys; no other change to ADR-003.

**Relationship to ADR-006 (graph schema).** ADR-006 should specify the `complexity` attribute as `Mapping[str, int]` open-set on the relevant node types. No enumerated key list — keys are governed by ADR-004 and additive.

**Relationship to downstream consumers (ADR-005, ADR-009, ADR-017).** These ADRs each cite specific rows of the Reference Threshold Table when applying cuts. Example forward references:
* ADR-005 (token strategy): expected to cite Method LoC = 100 (SonarSource `java:S138`) when deciding chunked vs single-prompt extraction.
* ADR-009 (rendering budget cap): expected to cite CBO ≥ 5 (Lanza & Marinescu 2006) and WMC ≥ 20 (same) when ranking class-selection candidates.
* ADR-017 (eval): expected to use raw values in a weight curve rather than cuts.

**What this ADR consciously does not do:**
* Define a "score" / "rank" that aggregates across metrics. Aggregation is consumer-specific (eval weighting may use one shape; class selection another). No cross-metric formula is committed here.
* Define "code smell" detection (god class, anaemic domain, etc.). Those are LLM-extracted observations per ADR-003 §2, optionally informed by these metrics.
* Apply any cut. Every cut application lives in the consuming ADR.

**Deferred items (future work):**
* DIT, RFC, NOC — when a consumer use case justifies them.
* Cross-metric aggregation if a consumer pattern emerges.
* Tier labels in the graph (TP-a) if consumer demand emerges.
* Project-level metrics (instability, abstractness, distance from main sequence — Martin 1994). Out of scope for v1.

References:
* McCabe, T.J. (1976). "A Complexity Measure." *IEEE TSE* 2(4), 308–320.
* Watson, A.H. & McCabe, T.J. (1996). NIST SP 500-235 — "Structured Testing: A Testing Methodology Using the Cyclomatic Complexity Metric." https://www.nist.gov/publications/structured-testing-testing-methodology-using-cyclomatic-complexity-metric
* Chidamber, S.R. & Kemerer, C.F. (1994). "A Metrics Suite for Object Oriented Design." *IEEE TSE* 20(6), 476–493.
* Hitz, M. & Montazeri, B. (1995). "Measuring Coupling and Cohesion In Object-Oriented Systems." *Proc. Int. Symp. Applied Corporate Computing*.
* Campbell, G.A. (2018). "Cognitive Complexity: A new way of measuring understandability." SonarSource. https://www.sonarsource.com/docs/CognitiveComplexity.pdf
* Basili, V.R., Briand, L.C. & Melo, W.L. (1996). "A Validation of OO Design Metrics as Quality Indicators." *IEEE TSE* 22(10), 751–761.
* Lanza, M. & Marinescu, R. (2006). *Object-Oriented Metrics in Practice*. Springer.
* Martin, R.C. (2008). *Clean Code: A Handbook of Agile Software Craftsmanship*. Prentice Hall.
* SonarSource rules: `java:S1541` (CC), `java:S3776` (cognitive), `java:S138` (method LoC). https://rules.sonarsource.com/java/
* MADR template — https://github.com/adr/madr
