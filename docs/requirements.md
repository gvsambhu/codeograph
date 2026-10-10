# Requirements

The functional and non-functional requirements codeograph is built against. Architecture decisions
that implement them are recorded as ADRs under [`docs/adr/`](adr/README.md), and each ADR cites the
requirements it satisfies — so traceability runs from a decision back to its requirement, not the
other way round. Requirements here state *what* the system must do; they do not name the designs
that chose *how*, beyond the interface a user invokes.

**Requirement statements describe the target system.** They are not a changelog of what ships today.
What ships today is recorded once, in the [status table](#status), which is also the numeric index
into this document.

**Provenance.** These requirements have governed the project from its start; they were maintained
as project-plan material and first published as this document on 2026-08-05, after v1 shipped.
Publication date is not authorship date.

Identifiers are stable and are never reused. A retired requirement keeps its number so existing
references continue to resolve.

---

## 1. Purpose

Codeograph reads a Java/Spring Boot codebase and produces two things: a **deterministic knowledge
graph** of what is in it — structure, relationships, and named complexity metrics — and, driven from
that graph, **idiomatic source in another language stack**. An LLM layer sits on top to explain and
translate; it never becomes the authority on what the code *is*.

This document defines what the system must do for that to be true, and what it must promise never to
do.

## 2. Scope

**In scope.** Reading a Java/Spring Boot codebase supplied as a local directory, a git URL, or a zip
archive; extracting structure, framework semantics, and complexity deterministically; enriching that with
LLM-derived semantics kept separable from the deterministic output; rendering a selected subset into a target stack;
measuring the quality of both the graph and the rendered output; and the operational surface that
makes a run reproducible, inspectable, and bounded in cost.

**Out of scope.** Building, running, testing, or deploying the source project. Running, testing, or
deploying the rendered output — it is compile-checked (FR-7) and nothing further. Runtime or dynamic
analysis. Source languages other than Java — including other JVM languages
such as Kotlin. Security scanning, architecture governance, and same-language refactoring — mature
tools already cover those. Migrating data, infrastructure, or build pipelines. Any claim that rendered
output is production-ready without review.

## 3. Definitions

| Term | Meaning in this document |
|---|---|
| **Corpus** | The set of source files in scope for one run, after acquisition and discovery. Not the same as "the repository" — excluded and non-source files are not part of the corpus. |
| **Module** | A build unit within the corpus — a directory with its own build file. A single-module project has one; a multi-module project has several, each with its own source roots. |
| **Run** | One end-to-end invocation of the tool against one corpus, producing one output directory. |
| **Artefact** | An output the tool produces for a consumer: the run manifest, the knowledge graph, the annotations, the rendered source, and the evaluation scorecards and sidecars. |
| **Deterministic artefact** | An artefact produced with no LLM contribution to its content (FR-34). NFR-6 states the byte-reproducibility guarantee that applies to this class, and the environment envelope it holds within. |
| **Diagnostic record** | A file the tool writes for later inspection rather than as an output — the structured run log and the per-call telemetry. Not an artefact. |
| **Structural fact** | A fact readable from the source text without inference — what the code declares, and what it references. |
| **Knowledge graph** | The deterministic property graph of a corpus — the elements it declares, the relationships between them, and named complexity metrics on those elements. The node and edge taxonomy is fixed by a published schema (FR-7b), not by this document. |
| **Degraded** | A corpus file whose extraction fell short of full fidelity — reduced-extractor output, or no usable structure at all. A degraded file is still represented in the graph (FR-31). |
| **Semantic fact** | A conclusion about what code means or is for. It requires inference rather than reading. |
| **Enrichment** | LLM-derived semantic output about the graph — role, intent, summaries, migration hazards, corpus-level synthesis. Always advisory, and always separable from the deterministic output. |
| **Domain** | A grouping of classes used to partition the corpus for rendering, derived from the graph rather than assigned by an LLM. |
| **Render target** | A language/framework stack the graph can be rendered into, supplied by a renderer implementing the renderer interface (NFR-5). |
| **Idiomatic** | Output a competent engineer in the target stack would recognise as written for that stack — using its own framework conventions — rather than transliterated Java. |
| **Scorecard** | A machine-readable record of quality checks, each with an id, a result, a threshold, and the rationale for that threshold. |
| **Golden** | A committed known-good artefact for a pinned input, compared on every run so that any difference is caught. |
| **Execution envelope** | The declared, pinned environment within which byte-level reproducibility holds (NFR-6 AC-4). Determinism claims elsewhere in this document are made within it. |
| **Canonical form** | The single byte-level serialisation rule for an artefact (key ordering, separators, encoding, line ending) that makes byte-comparison and hashing meaningful. |

## 4. Assumptions

1. The user runs the tool locally against source they are entitled to read.
2. A JDK is available for full-fidelity parsing. (What the tool does when one is absent is an
   obligation, not an assumption — see FR-31.)
3. `git` is available when a git URL is supplied as input.
4. The target project's own build tooling is **not** invoked and need not be installed.
5. LLM access requires the user's own provider credentials, supplied through the environment; any
   run may be performed with the LLM layer switched off entirely.
6. Rendered output is a reviewable starting point, not a finished port.
7. The target stack's own toolchain is available when rendered output is compile-checked. (What the
   tool does when it is absent is an obligation, not an assumption — see FR-7 AC-4.)

---

## 5. Functional requirements

### 5.1 Source intake

#### FR-1 · Accept a Java/Spring Boot project regardless of its build system
The tool works without per-project configuration.
- **AC-1** Maven projects are accepted.
- **AC-2** Gradle projects are accepted.
- **AC-3** The build system detected for each module is recorded in the graph, and is never left
  unspecified.

#### FR-29 · Accept the source in the forms a codebase is handed over in
Input handling covers the real handover paths, not just the local checkout.
- **AC-1** A local directory path is accepted.
- **AC-2** A git URL is accepted and the repository is acquired.
- **AC-3** A `.zip` archive is accepted and extracted.
- **AC-4** Archive extraction is bounded and path-checked (FR-24 AC-1, AC-2).
- **AC-5** Source acquired into a temporary location is removed when the run ends.

#### FR-30 · Discover the in-scope sources of the project
Turning "a project" into "a known set of files" is a defined, inspectable step.
- **AC-1** Multi-module projects are enumerated, and every source file is labelled with the module it
  belongs to.
- **AC-2** Files excluded by the project's own ignore rules are not in the corpus, so custom output
  and generated-source directories are skipped without per-project configuration.
- **AC-3** Only source files reach the parser.
- **AC-4** Source in a language other than Java is excluded from the corpus, and the exclusion is
  visible in the run's output.

### 5.2 Deterministic extraction

#### FR-10 · Structural facts are extracted deterministically, not by an LLM
These facts are syntactic — readable from the source text without inference — so they must come out
identical on every run.
- **AC-1** No LLM call participates in producing any structural fact.
- **AC-2** The same corpus yields the same structural facts on re-run, within the execution envelope.

#### FR-31 · No source file is ever silently dropped
**Negative guarantee.** Every file in the corpus is represented in the graph, whatever went wrong
while reading it.
- **AC-1** Every file in the corpus yields a node that records which extraction produced it —
  including the limiting case where no usable structure could be extracted at all.
- **AC-2** A failure of the parsing machinery degrades the affected files; the run continues.
- **AC-3** The degradation is reported to the user at the end of the run, naming the affected files.
- **AC-4** Every degraded file is recorded in the run's output with the reason.

#### FR-32 · Framework semantics are interpreted, not merely captured
The graph carries Spring's meaning, not just its annotation text.
- **AC-1** Every annotation present in source is captured on the node it applies to.
- **AC-2** A documented subset is additionally *interpreted* — lifted to a structured field, an edge,
  or a hazard tag.
- **AC-3** The criterion determining that subset is documented, and is stated independently of the
  outcome it produces.
- **AC-4** Members generated by compile-time code generation (e.g. Lombok) are synthesised so the
  graph reflects the compiled shape of the class, not only its written text.

#### FR-40 · An unresolvable reference is recorded as unresolved, never dropped
**Negative guarantee.** A consumer reading the graph can tell "there is no call here" apart from
"there is a call we could not trace."
- **AC-1** A reference the tool cannot resolve to a known target is still emitted, marked unresolved.
- **AC-2** An absent edge therefore means the reference is absent from the source — never that
  resolution failed.
- **AC-3** Conditions that degrade resolution are reported to the user at the end of the run.
- **AC-4** Where the tool can identify a remediation for such a condition, the report names it.

#### FR-12 · Complexity is measured with named industry-standard metrics
- **AC-1** Each metric is named, and its computation method cites a published source.
- **AC-2** Every reference threshold value cites a published source — a paper or a published rule
  reference. No threshold is chosen from memory.
- **AC-3** Values are numeric; no subjective high/medium/low bucketing is emitted in place of a value.
- **AC-4** A metric that cannot be computed for a node is null, never guessed.

### 5.3 Semantic enrichment

#### FR-11 · Semantic facts are extracted by an LLM operating on the deterministic output
Service intent, domain boundaries, and migration hazards are inferred by the LLM layer. It works from
what deterministic extraction produced — the nodes, and the source locations they record — rather than
discovering code on its own.
- **AC-1** The enrichment layer produces semantic facts about individual nodes and about the corpus
  as a whole.
- **AC-2** Which nodes are enriched, and where their source is read from, are determined by the
  deterministic graph; the enrichment layer does not discover or parse code that extraction did not
  produce.
- **AC-3** Source loaded for enrichment is an input to that layer only; it never enters the
  deterministic graph.

#### FR-35 · Enrichment degrades; individual failures do not fail the run
**Negative guarantee.** A provider outage, rate limit, or oversized input costs quality rather than
the run — up to a defined bound (AC-6).
- **AC-1** A per-call enrichment failure does not stop the run.
- **AC-2** The failure is recorded.
- **AC-3** The affected node is marked un-enriched.
- **AC-4** An input too large for quality extraction is reduced rather than dropped.
- **AC-5** The reduction is recorded on the node.
- **AC-6** There is a defined threshold of enrichment failure past which the run fails loudly rather
  than emitting a substantially unenriched result.
- **AC-7** The full pipeline can be run with LLM passes disabled, producing the deterministic
  artefacts alone.

### 5.4 Output artefacts and their contracts

#### FR-34 · LLM output must not affect the deterministic artefact
**Negative guarantee — the central architectural property.** The knowledge graph is a function of the
corpus and the tool alone. Nothing an LLM returns, and nothing about whether an LLM was reachable,
may change a single byte of it.
- **AC-1** No LLM-derived value is written into the deterministic graph artefact.
- **AC-2** No LLM *call outcome* (success, failure, cache hit, skip) is recorded in the deterministic
  graph artefact.
- **AC-3** A run with enrichment disabled and a run with enrichment enabled produce byte-identical
  deterministic graphs for the same corpus.
- **AC-4** The deterministic output is separable: a consumer can obtain it on its own, byte-identically,
  with enrichment joined to it by node identity at consumption time.

#### FR-2 · Emit a structured knowledge graph, independent of any render target
The graph is the product, not an intermediate. Structure is extracted deterministically (FR-10);
semantic enrichment is layered on top of it (FR-11).
- **AC-1** The graph carries no target-language concepts.
- **AC-2** Every class in the corpus is present in the graph, whatever the rendering budget (FR-13).

#### FR-7b · The graph and annotation schemas are published, machine-readable contracts
Published, machine-readable schema files are the language-neutral source of truth for these artefacts.
- **AC-1** Every emitted graph and annotation file validates against its published schema at write time.
- **AC-2** Validity is re-checked independently by the graph scorecard (FR-7a).
- **AC-3** The schema is published as a committed artefact, so an external consumer can validate
  output without importing the producing package.

#### FR-20 · Every run writes a manifest and structured logs
- **AC-1** A run manifest is written into the output directory as the entry point to the run.
- **AC-2** Structured, machine-readable logs are written into the output directory for the same run.
- **AC-3** A run correlation identifier joins manifest, logs, and telemetry.
- **AC-4** Human-readable console output and the structured log file are emitted together; verbosity
  is controllable at invocation.

#### FR-33 · The manifest is an integrity contract over the run's artefacts
- **AC-1** The manifest indexes every artefact the tool produced in the output directory, except the
  manifest itself, which is the index.
- **AC-2** Pointers to artefacts produced by an earlier run against the same directory are retained
  when a later run rewrites the manifest.
- **AC-3** Each indexed artefact carries a SHA-256 of its committed bytes.
- **AC-4** A missing artefact is explicit — an absent hash never doubles as "this stage was skipped".
- **AC-5** A consumer can detect any post-run modification of an artefact from the manifest alone.

#### FR-28 · Each field in the graph schema is documented as deterministic or not

### 5.5 Rendering

#### FR-3 · Render the knowledge graph into idiomatic TypeScript/NestJS source
- **AC-1** The rendered project runs from a clean checkout under its default configuration, without
  manual repair.
- **AC-2** Each source class maps to an identifiable unit of the output, so source and output can be
  compared side by side.

#### FR-4 · Render the knowledge graph into idiomatic Go source
Same graph, different target — the proof that the graph is target-independent.
- **AC-1** FR-3's acceptance criteria apply, read against Go and its ecosystem conventions.

#### FR-5 · The render target is selectable at invocation, without a code change
- **AC-1** The set of available targets is discoverable at runtime.
- **AC-2** An unknown target fails before pipeline work begins.
- **Interface** `--target <name>`

#### FR-13 · Rendering output is capped per domain
Bounds token spend and keeps runs reproducible.
- **AC-1** A default cap applies when none is given, and its value is documented.
- **AC-2** A value of `0` disables the cap entirely.
- **AC-3** Selection at the cap is deterministic and documented (FR-14).
- **AC-4** The cap binding is reported to the user at the end of the run, naming the affected domains,
  so a capped output is never mistaken for a full run.
- **Interface** `--max-classes-per-domain N` — default 3

#### FR-14 · Selection under the cap is deterministic and documented
- **AC-1** The same corpus and cap select the same classes on every run, within the execution envelope.
- **AC-2** The ordering rule is documented. Where it uses thresholds, each cites a published source.
- **AC-3** The selection is auditable — what was selected, what was skipped, and by which rule.
- **AC-4** The partition of the corpus into domains is computed deterministically from the graph.

#### FR-36 · No source feature is ever silently dropped from rendered output
**Negative guarantee.** Anything the renderer cannot translate faithfully is visible in the output.
- **AC-1** An untranslatable feature surfaces as a reviewable placeholder carrying the original
  intent.
- **AC-2** Security-relevant features default to refusal, so a rendered endpoint is never silently
  less protected than its source.
- **AC-3** The encounter behaviour is configurable, and the permissive setting warns loudly.
- **AC-4** The set of features v1 translates, defers, and refuses is documented as a single matrix.

#### NFR-5 · Adding a target language requires no change to the analyzer or the core pipeline
- **AC-1** A new target is a new renderer package, a compile-check entry, and nothing else.
- **AC-2** Renderer-authoring documentation exists for a contributor adding one: a short section in
  the contributor guide, with the full guide landing alongside the second renderer.

### 5.6 Evaluation

#### FR-7 · Run code-quality evaluations per target and produce target-specific scorecards
- **AC-1** The rendered output is compile-checked with the target stack's own toolchain.
- **AC-2** Feature-translation coverage is measured against the documented feature matrix (FR-36 AC-4).
- **AC-3** An LLM judge scores output quality.
- **AC-4** A check that cannot run records an explicit skip with a reason; a skip is never reported
  as a pass.

#### FR-7a · Run graph-quality evaluations and produce a graph scorecard
Checks: structural completeness, relationship correctness, schema validity, internal consistency,
semantic accuracy, reproducibility, and golden-graph agreement.
- **AC-1** Each check records a result, the threshold applied, and the rationale for that threshold.
- **AC-2** Every check is deterministic within the execution envelope, or explicitly skipped with a reason.
- **AC-3** Scorecards are machine-readable artefacts a consumer can locate from the run's manifest.

#### FR-41 · Graph correctness is measured against a human-validated expectation
Well-formedness checks cannot detect a fact the extractor never produced. Measuring accuracy requires
a statement of what the graph *should* contain, derived from reading the source rather than from the
tool's own output.
- **AC-1** For at least one corpus, an expectation of the graph's contents is authored from the source
  and confirmed by a person, independently of what the tool emits.
- **AC-2** The expectation is never regenerated from tool output — capture would record the tool's own
  errors as correct.
- **AC-3** The expectation may be partial. Which entries have been confirmed is recorded, and accuracy
  is reported only over the confirmed set.
- **AC-4** Runs are compared against it, and every difference is classified as improvement, regression,
  or intentional change.
- **AC-5** The expectation covers both what deterministic extraction should find and what the semantic
  layer should conclude. The semantic comparison is tolerance-based, not exact.

> This is distinct from FR-7c. FR-7c detects **drift** — whether output changed between runs — using a
> baseline captured from the tool. FR-41 measures **correctness** — whether output is right — and
> cannot use a captured baseline for that purpose. A system can be perfectly stable and consistently
> wrong; only FR-41 detects it.

#### FR-18 · A scorecard over LLM-derived output records the exact model version that produced it
Exact version strings, never family names — so a score that moves can be attributed to the tool or to
the model.
- **AC-1** Where the artefact being scored was produced by an LLM, the scorecard records the model
  version and the prompt version that produced it.
- **AC-2** Where the artefact was produced deterministically, no model provenance is recorded, and its
  absence is not a gap.

#### FR-9 · Ship at least one complete example run per target, with committed output and scorecards
- **AC-1** The committed example includes the run's own output artefacts.
- **AC-2** It includes the graph scorecard and the target scorecard.
- **AC-3** For a render target, it includes the rendered source.
- **AC-4** Example output is illustrative, not a byte-equal regression golden (FR-7c).

#### FR-25 · An LLM-judge calibration suite discriminates known-good from known-bad output at documented thresholds, committed as a calibration record

#### NFR-3 · Evaluation results are reproducible
A past score can be re-derived from what the scorecard records.
- **AC-1** A scorecard records the seed used to produce it.
- **AC-2** Where the scored artefact was LLM-derived, the provenance FR-18 records is available for
  re-derivation.

### 5.7 LLM platform control

#### FR-8 · Provider and model are both selectable, and neither is allowlisted
Two independent axes: which provider runs the call, and which model it runs.
- **AC-1** The provider is selectable without a code change.
- **AC-2** Any OpenAI-compatible endpoint is reachable by configuration alone, with no vendor
  allowlist in code.
- **AC-3** Any model id is accepted as free-form pass-through — no project-blessed allowlist.
- **AC-4** Per-pipeline-stage model overrides are available, each falling back to the single
  configured default.
- **Interface** `CODEOGRAPH_LLM_PROVIDER` — `anthropic | openrouter | openai_compatible` in v1;
  `ollama` and `bedrock` follow.

#### FR-15 · Prompts are versioned artefacts, not inline strings
- **AC-1** Each prompt version is a distinct, reviewable file; editing one in place is not how a new
  version is made.
- **AC-2** The production default for a prompt is declared explicitly, so promotion is a visible diff.
- **AC-3** A prompt declares the inputs it requires, and a missing or unknown input fails before the
  call is made.

#### FR-16 · Every LLM call emits telemetry
- **AC-1** Each call records: run id, provider, model, prompt identity, prompt version, input tokens,
  output tokens, cost estimate, latency, and timestamp.
- **AC-2** Per-call records are written to a machine-readable record, separate from the manifest, that
  can be inspected without an external service.
- **AC-3** Aggregate statistics roll into the run manifest.

#### FR-17 · LLM responses are cached content-addressed
- **AC-1** The cache key covers everything that would change the response — provider, model, prompt
  version, rendered prompt, and input hash — and nothing that would not.
- **AC-2** A stale entry is never served after any of those change.
- **AC-3** Cache hits are recorded in telemetry.

#### FR-37 · The response cache is inspectable and user-managed
- **AC-1** The user can report cache size, entry count, and hit behaviour.
- **AC-2** The user can purge selectively — by age, by model, by prompt version, or entirely.
- **AC-3** Nothing is evicted by surprise; growth is surfaced as an advisory, and reproducibility of
  a past run is never broken without the user acting.

#### FR-39 · LLM spend is bounded before a run starts and while it runs
No first run can launch an unbounded paid fan-out.
- **AC-1** A pre-flight estimate of call count and cost is shown before any paid work begins, and is
  labelled as an estimate from a dated table, not a quote.
- **AC-2** Above a configurable call-count threshold, an interactive run asks for confirmation.
- **AC-3** A non-interactive run never hangs on that prompt and never silently proceeds past it.
- **AC-4** Optional hard ceilings on total calls and total tokens abort the run mid-flight, reporting
  what was completed.
- **Interface** `--max-llm-calls`, `--max-tokens-total`, `--llm-call-confirm-threshold`, `--yes`,
  `--non-interactive`

#### FR-22 · Cost is estimated and capped in dollars
The permanent budget surface, superseding the call-and-token floor of FR-39.
- **AC-1** A dry run estimates cost without making paid calls.
- **AC-2** A hard spend ceiling stops the run on projected or accumulated spend.
- **Interface** `--dry-run`, `--max-cost-usd`

#### NFR-2 · A defined token-utilization strategy governs LLM input construction
- **AC-1** Repeated prompt prefixes are not re-billed per call.
- **AC-2** Token use and cost per run are surfaced to the user.

### 5.8 Configuration and run safety

#### FR-38 · Configuration is layered, with an explicit and predictable precedence
This is the falsifiable form of "the tool is configurable".
- **AC-1** Settings resolve in a documented order: invocation flags, then environment, then local
  environment file, then project config file, then built-in defaults.
- **AC-2** Configuration is validated at startup; a misconfiguration fails before work begins, not
  mid-run.
- **AC-3** Secrets are read only from the environment and the local environment file, never from the
  committed config file.
- **AC-4** A committed example environment file documents every credential a contributor must set.

#### FR-27 · Output-path safety
- **AC-1** All run artefacts are written inside the output directory.
- **AC-2** An output directory that is the working directory, or an ancestor of it, is rejected.
- **AC-3** Re-running against the output of a previous run does not require `--force`.
- **AC-4** Content the tool did not produce is never deleted.
- **AC-5** Content the tool did not produce is overwritten only where its path matches a file this run
  would write, and only with `--force`.
- **Interface** `--force`

#### FR-26 · Prompt-injection mitigation
Source text reaching an LLM is treated as data, never as instruction — content crafted to look like
an instruction does not change what the model is asked to do.

### 5.9 Engineering assurance

#### FR-19 · A test suite covers unit and integration behaviour, and CI blocks merge on failure
- **AC-1** Unit and integration layers are separated and independently runnable.
- **AC-2** Unit-test coverage is at or above 80%, enforced as a hard gate.
- **AC-3** No test requires a live LLM provider or network access.

#### FR-7c · The deterministic graph is regression-tested against committed goldens
- **AC-1** A golden is committed for a hand-built edge-case fixture corpus.
- **AC-2** A golden is committed for a pinned real Spring project. *(v1.1 — the harness ships with the
  fixture corpus alone; the real-project corpus follows.)*
- **AC-3** CI diffs every run byte-equal in canonical form.
- **AC-4** A golden refresh is deliberate, never incidental.
- **AC-5** Each refresh records its diff category: update-golden, fix-bug, or intentional-change.
- **Interface** `pytest --update-goldens`

#### FR-23 · Rendered output is byte-stable for a fixed input
With cached LLM responses held constant, re-rendering the same graph produces identical bytes.
Unexplained drift fails CI.

#### FR-24 · Negative tests assert graceful failure with specific error messages
These malformed-input classes at minimum, each failing loudly and actionably:
- **AC-1** *Zip bomb* — extracted size exceeds the configured cap; abort with a size-limit error before
  extraction completes.
- **AC-2** *Zip path traversal* — an archive entry resolves outside the extraction root; reject the
  archive.
- **AC-3** *Corrupt or malformed archive* — input is not a readable archive; return a clear error.
- **AC-4** *Acquisition failure* — the source cannot be fetched, or the URL is unreachable or
  credential-gated; return an actionable error naming the cause.
- **AC-5** *Empty corpus* — no `.java` files remain in scope after discovery; fail loudly with a
  user-readable message and a non-zero exit, never an empty-graph pass-through.
- **AC-6** *No recognised build file* — neither a Maven nor a Gradle build file is present; reject the
  corpus with a clear error rather than recording an unknown build system.

#### FR-21 · Secret scanning runs in CI on every push and pull request; merges are blocked on detection
- **AC-1** A secret scan runs on every push and every pull request.
- **AC-2** A detection blocks the merge, with no maintainer bypass.
- **AC-3** The scanner version is exactly pinned, and a check fails when the pin drifts.
- **AC-4** A full-history scan runs on a schedule, independently of per-commit scanning.

#### NFR-4 · CI runs lint, unit tests, and the evaluation path on every push
- **AC-1** Lint and unit tests gate merge.
- **AC-2** The evaluation path runs per committed example corpus and its scorecards are retained.
- **AC-3** The evaluation path exercises each shipped render target's own toolchain.

#### NFR-6 · The deterministic artefacts are byte-reproducible
Re-running the tool on the same corpus with the same version, within the declared execution
environment (AC-4), produces byte-identical deterministic artefacts.
- **AC-1** A single canonical serialisation rule governs those artefacts — key ordering, separators,
  encoding, and line ending.
- **AC-2** The canonical bytes are what is hashed for integrity (FR-33 AC-3), so one mechanism serves
  both comparison and integrity.
- **AC-3** No machine-specific value — absolute path, timestamp, locale, or iteration order — reaches
  a deterministic artefact.
- **AC-4** The execution environment under which byte-equality holds is declared and pinned. Drift
  from it is detected and stops the comparison, rather than being reported as a difference in output.

#### NFR-7 · Artefact schema versions are governed independently of the application version
Consumers pin the format, not the tool.
- **AC-1** Every emitted artefact's schema version is declared in the run's manifest, independently
  per artefact.
- **AC-2** Artefact schema versions and the application version are separate version lines; neither
  implies the other.
- **AC-3** Within a major schema line, evolution is additive, so an existing consumer keeps working.
- **AC-4** A breaking change to an artefact's shape requires a major bump of that artefact's schema
  version.

---

## 6. Retired identifiers

- **NFR-1** — **Retired.** No longer tracked as a requirement. The number is retained so existing
  references resolve.

---

## 7. Status

This table records what ships today. `shipped` · `partial` · `planned` · `retired`.

A requirement targeted at a future release may carry no acceptance criteria; its criteria are written
when the design that satisfies it is decided. A `shipped` or `partial` requirement must carry criteria —
this table cites them by number, and a status of `partial` is not expressible without them.

| ID | Status | Target | Note |
|---|---|---|---|
| FR-1 | shipped | v1 | Maven and Gradle both accepted. Gradle classpath resolution falls back to source-only, so method-call resolution is lower fidelity |
| FR-2 | shipped | v1 | |
| FR-3 | partial | v1 | AC-2 holds — per-class render granularity plus a deterministic project scaffold; full method bodies, not skeletons. AC-1 is not yet verified — the compile check runs the type-checker only, and no check installs or starts the rendered app |
| FR-4 | planned | v1.1 | |
| FR-5 | shipped | v1 | `--target` on `render`; `--list-targets` enumerates |
| FR-6 | retired | v1 | Retired 2026-08-23. Clause 1 (*a common renderer interface*) was ADR-008's mechanism, not an obligation; clause 2 (*no target-specific code in the core pipeline*) duplicated **NFR-5**, which carries it with acceptance criteria |
| FR-7 | partial | v1 | **AC-1 not met** — the compile check reads the manifest's `1.x` nested location for its sidecar pointer, which the `2.0.0` schema moved to a top-level peer, so it returns `skip` regardless of whether a render happened; its sidecar path also resolves against the run directory while the file is written to the render directory. AC-2 skips pending the render-time producer for its input. AC-3 llm_judge deferred |
| FR-7a | partial | v1 | **The statement's seven-check list is not fully met** — six of seven run; `semantic_accuracy` returns an explicit skip pending judge calibration, which is AC-2's permitted form, so no AC is breached. Separately, `structural_completeness` runs but its ground-truth source is an open question — a completeness ratio can only count declarations the extractor produced, so a declaration it never saw is absent from both sides. FR-41 is the intended oracle |
| FR-7b | shipped | v1 | Graph and annotation schemas published; manifest schema published and CI-gated against drift |
| FR-7c | shipped | v1 | AC-1 and AC-3 hold — the hand-built fixture corpus golden is committed and CI-gated byte-equal. **AC-2 is correctly deferred**, not missing: the real-project corpus and its golden were moved to v1.1 by design, and the fixture golden satisfies the v1 drift guardrail. AC-4 and AC-5 are obligations on the refresh procedure and are not separately verified here |
| FR-8 | shipped | v1 | `anthropic`, `openrouter`, `openai_compatible` live; `ollama` and `bedrock` wired in the resolver but raise `NotImplementedError`. Per-stage overrides present; no curated differential mapping |
| FR-9 | partial | v1 | **AC-1 and AC-3 not met; AC-2 partially met** — two committed example corpora ship a graph scorecard each; no committed run output, target scorecard, or rendered source. AC-4 holds |
| FR-10 | shipped | v1 | |
| FR-11 | shipped | v1 | |
| FR-12 | shipped | v1 | Cyclomatic, cognitive, WMC, CBO, LCOM4, MLOC — each cited; null where not computable |
| FR-13 | partial | v1 | Default 3 ships. AC-2 not yet met — `0` is currently rejected rather than disabling the cap |
| FR-14 | shipped | v1 | Stratified selection with cited thresholds; audit fields persisted |
| FR-15 | partial | v1 | Versioned prompt files with content-hash pinning ship. **AC-3 not verified** — the prompt input-contract check is not separately confirmed. *(The scorecard `prompt_id` gap moved to FR-18 AC-1, which owns provenance.)* |
| FR-16 | partial | v1 | **AC-1 not met** — cost estimate is hardcoded `0.0`; the field exists, the value is never computed. AC-2 and AC-3 hold: all other fields are emitted to the sidecar JSONL and aggregates roll into the manifest |
| FR-17 | shipped | v1 | SQLite content-addressed store; key covers all response-affecting inputs |
| FR-18 | partial | v1 | AC-2 holds — the graph scorecard records no model provenance, correctly, since its subject is deterministic. **AC-1 unmet**: the code scorecard grades LLM-rendered source and its `model_version` / `prompt_id` fields, present in both the model and the published schema, are never populated |
| FR-19 | shipped | v1 | `--cov-fail-under=80` enforced in CI; mock provider, no live calls |
| FR-20 | shipped | v1 | `manifest.json` + `logs.jsonl` in the output directory; `run_id` correlates; dual-channel emission with `-v`/`-q`/`--log-level` |
| FR-21 | shipped | v1 | Exact-pinned gitleaks in CI with a parity check and a nightly full-history scan; no admin bypass |
| FR-22 | planned | v1.1 | FR-39's call-and-token floor stands in for v1; FR-39 is retired when this lands |
| FR-23 | planned | v1.1 | |
| FR-24 | planned | v1.1 | |
| FR-25 | planned | v1.1 | |
| FR-26 | planned | v1.1 | |
| FR-27 | partial | v1 | AC-1 holds — telemetry, the one output written outside the directory, is a diagnostic record rather than an artefact (§3). AC-2's cwd-or-ancestor rejection is verified. AC-4 and AC-5 hold today only incidentally: nothing is overwritten or deleted without `--force`, so foreign content is protected by a rule that protects everything. **AC-3 not met** — a re-run against a previous run's output is refused unless `--force` is given. |
| FR-28 | planned | v1.1 | |
| FR-29 | shipped | v1 | Local, git, and zip acquirers all present |
| FR-30 | partial | v1 | AC-1, AC-2 and AC-3 hold — multi-module enumeration with module labelling, ignore-rule-driven exclusion, `.java`-only parsing. **AC-4 not met** — the Kotlin source root is dropped silently, with no log, warning, or record in the run's output |
| FR-31 | partial | v1 | AC-1, AC-2 and AC-4 hold — the AST → regex → name-only stub ladder runs, the run continues on parser failure, and each degraded file records its extraction mode. **AC-3 not met** — fallback is logged per file (`parser/file_parser_dispatcher.py:74`); no run-level report names the affected files, which is what ADR-003's amendment specifies |
| FR-32 | shipped | v1 | Interpretation runs inside the parser; interpreted set documented with its membership criterion |
| FR-33 | partial | v1 | AC-3, AC-4 and AC-5 hold — SHA-256 on every present pointer; skipped LLM passes signalled by an explicit flag, not a null hash. **AC-1 not met** — the rendered source is an artefact (§3) and is not indexed; the manifest's `artefacts` map holds only the graph and the annotations. **AC-2 not met** — a re-run resets the scorecard and compile-check pointer maps |
| FR-34 | shipped | v1 | Enforced as a file boundary — the deterministic graph carries no LLM-derived value and no call outcome |
| FR-35 | shipped | v1 | Per-call skip, oversized-input reduction, configurable abort ratio, and a full LLM-off mode |
| FR-36 | shipped | v1 | Placeholder/refuse policies configurable, security defaulting to refuse. The bundled preset flags are not on the CLI; policies are set through configuration |
| FR-37 | shipped | v1 | `cache stats`, `cache purge` (dry-run by default), `cache report` |
| FR-38 | shipped | v1 | Precedence documented in the committed config file and enforced by the settings layer |
| FR-39 | shipped | v1 | Pre-flight estimate from a dated local price table, TTY-aware confirmation gate, and mid-run call/token ceilings |
| NFR-1 | retired | — | Number retained so existing references resolve |
| NFR-2 | partial | v1 | Prefix caching ships. AC-2 token and cost scorecard not shipped, and blocked behind FR-16's uncomputed cost |
| NFR-3 | partial | v1 | AC-1 holds — the scorecard carries `seed`. **AC-2 not met** — the provenance FR-18 requires is unpopulated, so a past LLM-derived score cannot be re-derived; same root cause as FR-18 AC-1 |
| NFR-4 | partial | v1 | Lint, unit tests, and a per-corpus eval job all run. AC-3 not yet met — the eval job runs the deterministic path and does not invoke the target toolchain |
| NFR-5 | partial | v1 | The architecture holds — a renderer is a self-contained package behind a registry. **AC-1 not met** — `Scorecard.kind` is a hardcoded `Literal["graph","ts","go"]`, so a new target also requires editing the eval model. **AC-2 not met** — the renderer-authoring section is not yet written |
| FR-40 | shipped | v1 | The graph schema carries a `calls_unresolved` edge kind, so an unresolvable reference is emitted rather than dropped. AC-3's degraded-resolution reporting is decided (remediation hint on an unpopulated local Maven repository) but not separately verified here |
| FR-41 | planned | v1.1 | Not shipped in any form. FR-7c's harness detects drift against a captured baseline, which cannot serve as a correctness oracle. The two accuracy checks that need this expectation are `structural_completeness` (its ground-truth source is an open question) and `semantic_accuracy` (skipped, deferred) |
| NFR-6 | shipped | v1 | Canonical serialisation in the writer; the same bytes feed the manifest hash and the golden assertion |
| NFR-7 | shipped | v1 | Graph and manifest schema versions are independent of the application version; manifest is `2.0.0`, strict-additive within `2.x` |

---

## 8. Revision history

These requirements were first drafted before implementation began, and were revised during design
review as decisions sharpened or rescoped them. **This section closes at this document's first
commit** — from that point, the git history of this file is the record of change.

| Date | Requirement | Change | Driver |
|---|---|---|---|
| 2026-06-14 | FR-24 | "6+ malformed-input classes" enumerated as six named classes with required failure behaviours | design review; ADR-002 |
| 2026-06-19 | FR-8 | Provider set replaced — `anthropic \| ollama \| bedrock` became `anthropic \| openrouter \| openai_compatible`; `ollama` and `bedrock` moved to v1.1 | design review; ADR-013 |
| 2026-06-19 | FR-16 | `run_id` added to the telemetry payload as the manifest-to-logs correlation key; per-call records routed to a sidecar JSONL with aggregates in the run manifest | design review; ADR-015, ADR-022 |
| 2026-06-19 | FR-22 | Deferred to v1.1. v1 ships call and token ceilings with a confirmation gate in place of cost estimation and a spend ceiling | design review; ADR-027 |
| 2026-06-19 | NFR-2 | Token and cost scorecard deferred to v1.1. v1 commits graph scorecards and ships prefix caching | design review |
| 2026-06-19 | NFR-5 | Full renderer guide deferred to v1.1; v1 ships a short contributor-guide section. The guide waits on a second renderer to make the pattern real | design review; ADR-008 |
| 2026-06-29 | FR-8 | Generalised — the OpenAI-compatible provider accepts any base URL, with no vendor allowlist | design review; ADR-013 |
| 2026-08-05 | NFR-1 | Retired. Number retained so existing references resolve | — |

Three requirements moved from v1 to v1.1 during design review — FR-22, NFR-2 and NFR-5. In each case
v1 ships a narrower capability that meets the immediate need, and the fuller form is scheduled.
