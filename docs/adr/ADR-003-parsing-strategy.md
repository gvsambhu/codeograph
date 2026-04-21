---
status: "accepted"
date: 2026-04-21
decision-makers: Ganesh
consulted: —
informed: —
---

# ADR-003 — Parsing Strategy: AST Tool & AST-vs-LLM Split

## Context and Problem Statement

Stage 2 of the pipeline turns a set of enumerated Java sources (output of Stage 1, ADR-002) into structured facts the rest of the pipeline operates on. Two entangled choices sit inside this stage:

1. **Which AST tool** extracts structural facts from Java sources.
2. **How the workload is split between AST and LLM** — what is extracted deterministically by the parser vs what is extracted by the LLM from source.

Both choices shape cost, determinism, accuracy, and the shape of everything downstream (graph schema in ADR-006, complexity in ADR-004, token strategy in ADR-005, rendering in ADR-008+). They must be decided together because each tool choice constrains what the split can reasonably look like, and vice versa.

The initial implementation made the opposite choice along both axes: no AST, regex-only structural extraction with a hardcoded project-package prefix, and LLM-driven method-signature / complexity / metadata extraction. This ADR supersedes that approach end-to-end.

## Decision Drivers

* **Determinism first for structural facts.** Class names, method signatures, annotations, call edges, complexity numbers — these are syntactic. They must be extracted identically on every run for eval, golden-graph testing, and reproducible graphs.
* **LLM budget preservation.** Every token spent re-extracting a method signature the parser could have given us for free is a token not available for the work only the LLM can do (domain labelling, NL summaries, migration hazards).
* **Runtime realism.** The tool's users are Java engineers reviewing Java code; a Java 17+ JDK on their PATH is a reasonable expectation, consistent with peer tools (SonarQube, PMD, Checkstyle).
* **Graceful degradation on weird input.** Generated code, exotic JDK features, or partially invalid files should not fail the whole run.
* **Consistency with ADR-002.** Multi-module enumeration and the "detect + declare" build-system stance feed into what classpath the parser can assemble.

## Considered Options

**AST tool**
* T1 — JavaParser (JVM library)  *(chosen)*
* T2 — tree-sitter-java (native C, Python binding)
* T3 — javalang (pure-Python)
* T4 — ANTLR4 with a community Java grammar (pure-Python runtime)

**AST-vs-LLM split**
* S1 — AST-first, LLM-augment  *(chosen)*
* S2 — LLM-heavy with AST guardrails
* S3 — LLM-only
* S4 — Hybrid with escalation

**Failure policy when the AST parser rejects a file**
* F1 — skip the file + record in manifest
* F2 — fail the run
* F3 — per-file regex fallback (lifted + generalised from the initial implementation), degraded node flagged  *(chosen)*

**Classpath strategy for JavaParser symbol resolution**
* CP1 — source-only + JDK reflection (no build-file reading)
* CP2 — source-only + JDK reflection + Maven dep resolution from `~/.m2`  *(chosen)*
* CP3 — full build-file parsing for both Maven and Gradle

**Call-graph edge fidelity for unresolved targets**
* E1 — emit edge with `resolved: false` flag
* E2 — drop unresolved edges
* E3 — segregate: distinct edge types `resolved_call` vs `unresolved_call`  *(chosen)*

## Decision Outcome

### 1. AST tool — JavaParser via bundled JAR + JVM sidecar

* Codeograph ships a bundled JAR wrapping JavaParser. Python starts one long-lived Java subprocess per run and communicates via line-delimited JSON over stdin/stdout. JVM startup cost is amortised across the whole project (~one ~300ms hit per run, not per file).
* **Runtime requirement:** Java 17+ on PATH. Validated at startup with a clear error message pointing at the README.
* **ADR-002 amendment (footnote added in that ADR):** the pure-Python-runtime constraint is narrowed to "Codeograph must not shell out to the *target project's* build tooling (`gradle`, `mvn`, `gradlew`) to function." Parsing helpers that Codeograph bundles and controls are out of scope of the constraint.

### 2. Split — Archetype (i): AST-first, LLM-augment

**AST extracts (deterministic, free, every run):**
* package, imports, class / interface / enum / record declarations, modifiers
* field declarations with types and modifiers
* method signatures (name, params with types, return, throws, modifiers, generics)
* annotations — presence, args, target
* inheritance + implements edges
* call-site edges — resolved within project, unresolved as distinct edge type (E3)
* complexity per method — initial minimum: cyclomatic + cognitive (extended by ADR-004)
* Spring stereotypes from annotation nodes (`@Controller`, `@Service`, `@Repository`, `@Configuration`, `@Component`, `@RestController`)
* HTTP metadata from `@GetMapping` / `@PostMapping` / `@RequestMapping` arg extraction

**LLM extracts (semantic, per-class):**
* domain label (clusters classes into domains — "User management", "Payment", etc.)
* NL summary of class intent
* migration hazards specific to the target language (Spring idiom flags)
* quality observations (god class, anaemic domain, etc.) where applicable

**Explicitly not in v1:** cross-module ref resolution beyond JavaParser's native symbol solving (deferred from ADR-002), dead-code detection, Kotlin sources, test sources in the graph.

### 3. Parse failure — per-file regex fallback (F3)

When JavaParser cannot produce a usable AST for a file:
* Run a narrow regex-based extractor over that file (lifted from the initial implementation's `StaticDependencyExtractor`, generalised to derive the project base package from the enumerated source tree rather than a hardcoded prefix).
* The fallback extracts: class name, class kind, imports, class-level annotations, field types (Lombok-style DI), best-effort method-signature list, and a keyword-counted approximation of cyclomatic complexity.
* The resulting class node is tagged `extraction_mode: regex_fallback` so downstream consumers (eval, renderer) can treat it as lower-confidence.
* The file is recorded in the run manifest (ADR-022) with the parser's error message.
* The rest of the run proceeds on the AST path unaffected.

### 4. Classpath — source-only + JDK reflection + Maven from `~/.m2` (CP2)

JavaParser's symbol solver is assembled from three type solvers:
* `JavaParserTypeSolver` over every discovered `src/main/java` root (multi-module aware; feeds off Stage 1's output)
* `ReflectionTypeSolver` for JDK classes
* `JarTypeSolver` for each dep JAR resolved from a parsed `pom.xml` + `~/.m2/repository/` lookup, *when the project is Maven*

Consequences of this choice:
* **Within-project refs:** fully resolved into typed edges.
* **JDK refs:** fully resolved.
* **Third-party refs on Maven projects with a populated `~/.m2`:** resolved.
* **Third-party refs on Gradle projects, or Maven with empty `~/.m2`:** unresolved — emitted as `unresolved_call` edges with target = identifier only.

Documented as a v1 limit: Gradle projects see weaker symbol resolution than Maven projects in v1. Full Gradle dep resolution is a later ADR when prioritised.

### 5. Call-graph edges — segregated (E3)

The graph has two call-edge types (schema details in ADR-006):
* `resolved_call` — target is a known class/method in the graph
* `unresolved_call` — target is an identifier only; likely points into a framework / third-party lib

Consumers use the edge *type* to filter. Eval queries needing precision use `resolved_call` only; renderer and migration-hazard detection use `unresolved_call` to spot framework coupling.

### 6. Lombok synthesis pass

A post-parse pass walks class-level annotations and synthesises AST-equivalent nodes for Lombok-generated members. v1 coverage:
* `@Getter`, `@Setter` (including class-level and field-level)
* `@RequiredArgsConstructor`, `@AllArgsConstructor`, `@NoArgsConstructor`
* `@Data` (= `@Getter` + `@Setter` + `@RequiredArgsConstructor` + `@ToString` + `@EqualsAndHashCode`)
* `@Value` (immutable equivalent of `@Data`)
* `@Builder` (synthesises the nested `Builder` class and `builder()` entry point)

Out of scope for v1 (best-effort or skipped): `@SneakyThrows`, `@Slf4j` / other log-field injectors, `@With`, `@Delegate`, `@Accessors` customisations.

### 7. Intermediate output shape

ADR-003 defines the **intermediate** per-class structural-facts dataclass; the final graph schema is ADR-006's concern. Rough shape (subject to ADR-006 for the final serialised form):

```python
@dataclass(frozen=True)
class ClassFacts:
    module: str
    package: str
    class_name: str
    class_kind: Literal["class", "interface", "enum", "record", "annotation"]
    modifiers: list[str]
    annotations: list[AnnotationFact]
    extends: Optional[str]
    implements: list[str]
    fields: list[FieldFact]
    methods: list[MethodFact]
    stereotype: Optional[str]          # "Controller" | "Service" | "Repository" | ...
    extraction_mode: Literal["ast", "regex_fallback"]

@dataclass(frozen=True)
class MethodFact:
    name: str
    params: list[ParamFact]
    return_type: str
    throws: list[str]
    modifiers: list[str]
    annotations: list[AnnotationFact]
    http_metadata: Optional[HttpMetadataFact]
    complexity: dict[str, int]         # {"cyclomatic": N, "cognitive": M, ...} — ADR-004 extends keys
    calls: list[CallFact]              # mixed resolved + unresolved; edge type decided at graph assembly
```

### 8. Complexity metrics — minimum now, ADR-004 extends

ADR-003 reserves the AST layer as the locus of complexity computation and pins the **initial minimum** as cyclomatic + cognitive. Both have unambiguous definitions in the literature, both are standard, and both are implementable from the AST without extra input.

ADR-004 extends the set and pins thresholds with citations (per project guardrail — no threshold picked from memory). Extension is additive: each new metric becomes a new walker emitting a new key in the `complexity` dict. No ADR-003 revision required, no schema revision required.

### Consequences

* Good, because structural facts (signatures, annotations, call edges, complexity) are deterministic, free of token cost, and reproducible — underpinning golden-graph testing (ADR-007) and eval (ADR-017).
* Good, because LLM budget concentrates on work only an LLM can do — domain labelling, NL summaries, migration hazards.
* Good, because JavaParser's mature symbol solver delivers resolved within-project call edges without us building a name-resolution layer.
* Good, because the regex fallback means no file silently drops out of the graph; the failure mode is visible and labelled.
* Good, because the `resolved_call` / `unresolved_call` segregation preserves signal that the initial implementation's LLM-only pipeline couldn't capture — framework coupling is queryable.
* Bad, because Codeograph now requires Java 17+ on PATH at runtime. Documented expectation; peer tools have the same bar.
* Bad, because shipping a bundled JAR and a subprocess protocol adds engineering surface we own — serialisation schema, error handling, process lifecycle.
* Bad, because Gradle projects get second-class symbol resolution until a later ADR adds Gradle dep extraction. Flagged as a known v1 limit.
* Bad, because `~/.m2` being empty silently degrades Maven resolution — we document and detect but cannot auto-populate.
* Bad, because Lombok synthesis is a side-pass we maintain against Lombok's spec; Lombok feature changes require updates here.

### Confirmation

* **Unit:** fixture-based test per AST extractor (class / method / annotation / call / complexity / Lombok synthesis) asserting expected `ClassFacts` output.
* **Integration:** multi-module Maven fixture with a populated fake `~/.m2` — asserts resolved edges for within-project and third-party, unresolved for genuinely unknown targets.
* **Fallback:** inject a deliberately malformed `.java` file; assert the run completes, the file lands in the graph with `extraction_mode: regex_fallback`, and the manifest records the failure.
* **Lombok:** fixture with `@Data` / `@Builder` / `@RequiredArgsConstructor` classes; assert synthesised members match spec.
* **Runtime gate:** startup check that `java -version` returns ≥ 17, otherwise exit with a clear error and README link.

## Pros and Cons of the Options

### AST tool

**T1 — JavaParser** *(chosen)*
* Good, because only option with mature built-in symbol resolution (typed edges for within-project calls come for free).
* Good, because industrial use (10k+ stars, Java 21 support, active maintenance).
* Good, because error-tolerant parsing with file/line-precise error reporting.
* Bad, because JVM on the user's machine.
* Bad, because subprocess bridge is code we own.

**T2 — tree-sitter-java**
* Good, because pure native binding, no JVM.
* Good, because fast and error-tolerant.
* Bad, because concrete syntax tree only — no symbol resolution.
* Bad, because building a symbol table on top is a multi-week sub-project with its own bug surface.

**T3 — javalang**
* Good, because pure Python, zero runtime dep.
* Bad, because effectively unmaintained; Java 17+ features (records, sealed classes, pattern matching, switch expressions) break or mis-parse.
* Bad, because any modern Spring Boot 3 codebase will hit this.

**T4 — ANTLR4**
* Good, because pure Python runtime.
* Neutral, because grammar exists but quality and Java-spec-catchup depend on community maintenance.
* Bad, because slower than tree-sitter and no symbol resolution advantage over it.

### AST-vs-LLM split

**S1 — AST-first, LLM-augment** *(chosen)*
* Good, because minimises LLM tokens on facts the parser can produce for free.
* Good, because deterministic structural layer; LLM work isolated to genuinely semantic concerns.
* Good, because compatible with eval / golden-graph / caching strategies.
* Bad, because AST walker code to write and maintain. Justified by the cost and accuracy wins.

**S2 — LLM-heavy with AST guardrails**
* Good, because LLM can sometimes catch things AST misses.
* Bad, because 5-10× token cost of S1 for typically-redundant work (LLM re-producing signatures the AST already has).
* Bad, because structural facts become probabilistic; eval and golden-graph testing get harder.

**S3 — LLM-only**
* Bad, because everything non-deterministic; complexity numbers hallucinated; signatures wrong on generics and `throws`; no cost ceiling on large projects.
* This is essentially what the initial implementation did and the reason this ADR exists.

**S4 — Hybrid with escalation**
* Good, because best average cost with a confidence-gated escalation path.
* Bad, because more moving parts than v1 warrants. Reasonable v1.1 evolution on top of S1.

### Failure policy

**F1 — skip + record**
* Good, because simple.
* Bad, because classes silently missing from the graph.

**F2 — fail the run**
* Good, because loudest signal.
* Bad, because one weird generated file kills the whole run.

**F3 — per-file regex fallback** *(chosen)*
* Good, because no file silently disappears; graph coverage stays complete.
* Good, because degraded nodes are labelled, not pretending to be full-quality.
* Good, because the initial implementation's code is substantially liftable — a few hours of adaptation, not weeks.
* Bad, because carries a second extraction code path to maintain.

### Classpath

**CP1 — source-only + JDK**
* Good, because zero extra work.
* Bad, because every Spring / JPA / Lombok call becomes unresolved — big signal loss on the most important call targets for migration.

**CP2 — add Maven from `~/.m2`** *(chosen)*
* Good, because Maven is overwhelmingly the more common build system in Spring Boot projects; gains third-party resolution for the majority.
* Good, because `~/.m2` is already populated on any developer machine that has built the target project.
* Bad, because empty `~/.m2` degrades silently (documented + detected).
* Bad, because Gradle projects get no third-party resolution in v1 — acknowledged limit.

**CP3 — full build-file parsing for both**
* Good, because maximal symbol coverage.
* Bad, because Gradle parsing is the tar pit already rejected in ADR-002.

### Call-graph edges

**E1 — flag-based**
* Good, because single edge type, simpler schema.
* Bad, because consumer discipline required — every query needs to remember the flag.

**E2 — drop unresolved**
* Good, because cleanest graph.
* Bad, because migration-hazard detection loses its best signal (framework coupling).

**E3 — segregate** *(chosen)*
* Good, because schema carries intent; consumers filter by type not by flag.
* Good, because eval and renderer naturally query different edge types for different purposes.
* Neutral, because small schema cost absorbed in ADR-006.

## More Information

**Relationship to ADR-004 (complexity metrics).** ADR-003 reserves the AST layer as the locus of complexity computation. ADR-004 pins the full metric set and thresholds with citations. Extension is additive — ADR-003 needs no revision when ADR-004 adds metrics.

**Relationship to ADR-002.** ADR-003 consumes `ProjectInput` from Stage 1, including the `build_system` label, multi-module layout, and filtered source list. The Maven `pom.xml` classpath reader lives in ADR-003's scope (not ADR-002's), since its purpose is parser classpath assembly, not project-level metadata extraction.

**What the initial implementation got right (carried forward):**
* `DependencyExtractor` pattern — ABC with pluggable implementations. Kept as the AST / fallback dispatch interface.
* Two-pass structure (per-class extraction → cross-class/domain synthesis). Reasonable shape, retained.
* LLM used for genuinely semantic work (domain labelling, NL summaries). Kept; scope narrowed.

**What the initial implementation got wrong (fixed here):**
* No AST at all — fixed (JavaParser).
* Hardcoded project-package prefix in imports regex — fixed (fallback derives it dynamically).
* LLM extracting method signatures and "judging" complexity — fixed (AST owns both).
* Framework detection via naked string match — fixed (annotation-node inspection on AST).
* Call graph absent from output — fixed (resolved + unresolved edges).

**Deferred / future ADRs:**
* Gradle dep resolution for third-party classpath (v1.1 or later dedicated ADR).
* Cross-module ref resolution beyond JavaParser's native reach (where modules import each other's internal symbols via reflection / dynamic mechanisms) — if ever needed.
* Kotlin source support.
* Dead-code detection via whole-project reachability.

References:
* JavaParser — https://javaparser.org/
* JavaParser Symbol Solver — https://www.javadoc.io/doc/com.github.javaparser/javaparser-symbol-solver-core/
* MADR template — https://github.com/adr/madr
