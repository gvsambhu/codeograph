# Requirements

The functional and non-functional requirements codeograph is built against. Architecture decisions
that implement them are recorded as ADRs under [`docs/adr/`](adr/README.md), and each ADR cites the
requirements it satisfies. The link is recorded in the ADR only: a requirement statement never names an
ADR, so a new or superseded design never reopens a requirement. The status and history tables may cite
ADRs as evidence. Requirements here state *what* the system must do; they do not name the designs that
chose *how*, beyond the interface a user invokes.

Where a requirement has a user-facing surface, an `Interface` line names it; the criteria never do. A
requirement labelled **Negative guarantee** states something the system must never do.

**Requirement statements describe the target system.** They are not a changelog of what ships today.
What ships today is recorded once, in the [status table](#7-status), which is also the numeric index
into this document.

**Provenance.** The first set — FR-1 to FR-28 and NFR-1 to NFR-5 — was written in the project plan,
outside this repository, before implementation began, and governed the initial implementation. It was
added to this repository as this document on 2026-08-06, after the first scope was built. Requirements
added since record obligations the first set left unstated, or guarantees added later; this file's git
history dates each one (§8).

Identifiers are permanent and are never reused. A retired requirement keeps its number so existing
references continue to resolve. Acceptance-criterion numbers are never reused or renumbered either: a
removed criterion leaves its number unused. A new requirement takes the next free number; a letter
suffix (FR-7a) marks a requirement split from an earlier one and kept beside it. The sections group
requirements by topic, so numbers are not in order — the status table lists them in order.

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
archive; extracting structure, framework semantics, and complexity deterministically; adding LLM-derived
enrichment, kept separable from the knowledge graph; rendering a selected subset into a target stack;
measuring the quality of both the graph and the rendered source; and the operational surface that
makes a run reproducible, inspectable, and bounded in cost.

**Out of scope.** Building, running, testing, or deploying the source project. Running, testing, or
deploying the rendered source — it is compile-checked (FR-7) and nothing further. Runtime or dynamic
analysis. Source languages other than Java — including other JVM languages
such as Kotlin. Security scanning, architecture governance, and same-language refactoring — mature
tools already cover those. Migrating data, infrastructure, or build pipelines. Any claim that rendered
source is production-ready without review.

## 3. Definitions

Terms are ordered so that each is defined before it is used, except *invocation*, *output directory*, *run* and
*corpus*, which are defined in terms of one another.

| Term | Meaning in this document |
|---|---|
| **Invocation** | One execution of any of the tool's commands against an output directory. |
| **Output directory** | The directory a run writes to, and that every later invocation against the run writes to. |
| **Run** | One end-to-end invocation of the tool against one corpus, producing one output directory. |
| **Corpus** | The set of source files in scope for one run, after acquisition and discovery. Not the same as "the repository" — excluded and non-source files are not part of the corpus. |
| **Module** | A build unit within the corpus — a directory with its own build file. A single-module project has one; a multi-module project has several, each with its own source roots. |
| **Superseded output** | Output that a later invocation has replaced, or whose inputs have changed since it was produced. |
| **Structural fact** | A fact readable from the source text without inference — what the code declares, and what it references. |
| **Semantic fact** | A conclusion about what code means or is for. It requires inference rather than reading. |
| **Knowledge graph** | The property graph the tool extracts from a corpus — the elements it declares, the relationships between them, and named complexity metrics on those elements. The node and edge taxonomy is fixed by a published schema (FR-7b), not by this document. |
| **Degraded** | A corpus file whose extraction fell short of full fidelity — reduced-extractor output, or no usable structure at all (FR-31). |
| **Enrichment** | LLM-derived semantic output about the graph — role, intent, summaries, migration hazards, corpus-level synthesis. |
| **Scorecard** | A machine-readable record of quality checks, each with an id, a result, a threshold, and the rationale for that threshold. |
| **Artefact** | An output the tool produces for a consumer: the run manifest, the knowledge graph, the enrichment, the rendered source, the evaluation scorecards, and the compile-check record. |
| **Deterministic artefact** | The class of artefacts FR-34 and NFR-6 constrain — in this version, the knowledge graph alone. |
| **Canonical form** | The single byte-level serialisation rule for an artefact (key ordering, separators, encoding, line ending) that makes byte-comparison and hashing meaningful. |
| **Execution envelope** | The declared, pinned environment within which byte-level reproducibility holds (NFR-6 AC-4). Determinism claims elsewhere in this document are made within it. |
| **Golden** | A committed known-good artefact for a pinned input (FR-7c). |
| **Diagnostic record** | A file the tool writes for later inspection rather than as an output — the structured run log, the per-call telemetry, and the invocation history (FR-43). Not an artefact. |
| **Prompt** | The instruction text the tool sends to an LLM with each call. It ships with the tool; it is not an artefact. |
| **Domain** | A grouping of classes used to partition the corpus for rendering (FR-14). |
| **Render target** | A language/framework stack the graph can be rendered into (FR-3, FR-4, NFR-5). |
| **Idiomatic** | Output a competent engineer in the target stack would recognise as written for that stack — using its own framework conventions — rather than transliterated from the source language. |

## 4. Assumptions

1. The user runs the tool locally against source they are entitled to read.
2. A JDK is available for full-fidelity parsing. (What the tool does when one is absent is an
   obligation, not an assumption — see FR-31.)
3. `git` is available when a git URL is supplied as input.
4. The source project's own build tooling is **not** invoked and need not be installed.
5. LLM access requires the user's own provider credentials, supplied through the environment; any
   run may be performed with no LLM calls at all.
6. Rendered source is a reviewable starting point, not a finished port.
7. The target stack's own toolchain is available when rendered source is compile-checked. (What the
   tool does when it is absent is an obligation, not an assumption — see FR-7 AC-4.)

---

## 5. Functional requirements

### 5.1 Source intake

#### FR-1 · Accept a Java/Spring Boot project whichever supported build system it uses
The tool works without per-project configuration.
- **AC-1** Maven projects are accepted.
- **AC-2** Gradle projects are accepted.
- **AC-3** The build system detected for each module is recorded in the graph, and is never left
  unspecified.
- **AC-4** A supported project is processed without configuration specific to that project.

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
- **AC-4** Source in a language the tool does not read is excluded from the corpus, and the exclusion is
  visible in the run's output.

#### FR-24 · Unusable input fails with an error that names the cause
Each class below fails with the failure outcome (FR-45) and an error naming the cause; at minimum:
- **AC-1** *Zip bomb* — extracted size exceeds the configured cap; extraction stops before it completes.
- **AC-2** *Zip path traversal* — an archive entry resolves outside the extraction root; the archive is
  rejected.
- **AC-3** *Corrupt or malformed archive* — the input is not a readable archive.
- **AC-4** *Acquisition failure* — the source cannot be fetched, or the URL is unreachable or
  credential-gated.
- **AC-5** *Empty corpus* — no source files remain in scope after discovery; never an empty-graph
  pass-through.
- **AC-6** *No recognised build file* — neither a Maven nor a Gradle build file is present; never
  recorded as an unknown build system.

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
The graph carries the framework's meaning, not just its annotation text.
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
- **AC-3** Conditions that reduce how many references can be resolved are reported to the user at the end
  of the run.
- **AC-4** Each condition reported under AC-3 states its remediation, or states that none is known.

#### FR-12 · Complexity is measured with named industry-standard metrics
- **AC-1** Each metric is named, and its computation method cites a published source.
- **AC-2** Every reference threshold value cites a published source — a paper or a published rule
  reference. No threshold is chosen from memory.
- **AC-3** Each computed metric value is a number.
- **AC-4** A metric that cannot be computed for a node is recorded as not computed, never guessed.

### 5.3 Semantic enrichment

#### FR-11 · Semantic facts are extracted by an LLM operating on the knowledge graph
Service intent, domain boundaries, and migration hazards are inferred by an LLM. Enrichment works from
what deterministic extraction produced — the nodes, and the source locations they record — rather than
discovering code on its own.
- **AC-1** Enrichment produces semantic facts about individual nodes and about the corpus as a whole.
- **AC-2** Which nodes are enriched, and where their source is read from, are determined by the
  knowledge graph; enrichment does not discover or parse code that extraction did not produce.
- **AC-3** Source loaded for enrichment is an input to enrichment only; it never enters the knowledge
  graph.

#### FR-35 · An enrichment failure costs quality, not the run
**Negative guarantee.** A provider outage, rate limit, or oversized input costs quality rather than
the run — up to a defined bound (AC-6).
- **AC-1** A per-call enrichment failure does not stop the run.
- **AC-2** The failure is recorded.
- **AC-3** The affected node is marked un-enriched.
- **AC-4** An input too large for quality extraction is reduced rather than dropped.
- **AC-5** The reduction is recorded on the node.
- **AC-6** There is a defined threshold of enrichment failure past which the run fails loudly rather
  than emitting a substantially unenriched result.
- **AC-7** The full pipeline can be run with enrichment disabled, producing the deterministic
  artefacts alone.

### 5.4 Output artefacts and their contracts

#### FR-34 · LLM output must not affect the deterministic artefact
**Negative guarantee — the central architectural property.** The knowledge graph is a function of the
corpus, the tool and its recorded extraction settings alone. Nothing an LLM returns, and nothing about whether an LLM was reachable,
may change a single byte of it.
- **AC-1** No LLM-derived value is written into the knowledge graph.
- **AC-2** No LLM *call outcome* (success, failure, cache hit, skip) is recorded in the knowledge
  graph.
- **AC-3** A run with enrichment disabled and a run with enrichment enabled produce byte-identical
  knowledge graphs for the same corpus.
- **AC-4** The knowledge graph is separable: a consumer can obtain it on its own, byte-identically,
  with enrichment joined to it by node identity at consumption time.

#### FR-2 · Emit a structured knowledge graph, independent of any render target
The graph is an output in its own right, for a consumer who never renders — not only a step on the way
to rendered source. Structure is extracted deterministically (FR-10);
semantic enrichment is layered on top of it (FR-11).
- **AC-1** The graph carries no target-language concepts.
- **AC-2** Every class in the corpus is present in the graph, whatever the rendering budget (FR-13).

#### FR-7b · The graph and enrichment schemas are published, machine-readable contracts
Published, machine-readable schema files are the language-neutral source of truth for these artefacts.
- **AC-1** Every emitted graph and enrichment file validates against its published schema at write time.
- **AC-2** Validity is re-checked independently by the graph scorecard (FR-7a).
- **AC-3** The schema is published as a committed artefact, so an external consumer can validate
  output without importing the producing package.

#### FR-20 · Every run writes a manifest and a structured run log
- **AC-1** A run manifest is written into the output directory as the entry point to the run.
- **AC-2** A structured, machine-readable run log is written into the output directory for the same run.
- **AC-3** A run correlation identifier joins the manifest, the structured run log, and the LLM-call
  telemetry (FR-16).
- **AC-4** Human-readable console output and the structured run log are emitted together; verbosity
  is controllable at invocation.

#### FR-33 · The manifest is an integrity contract over the run's artefacts
- **AC-1** The manifest indexes every artefact produced by an invocation against the output directory
  that has not since been superseded, including a rendered source written outside it, except the
  manifest itself, which is the index.
- **AC-2** Pointers to artefacts produced by an earlier invocation against the same directory are
  retained when a later invocation rewrites the manifest, unless the later invocation supersedes them.
- **AC-3** Each indexed artefact carries a cryptographic hash of its committed bytes.
- **AC-4** A missing artefact is explicit — an absent hash never doubles as "this stage was skipped".
- **AC-5** A consumer can detect any post-run modification of an artefact from the manifest alone.
- **AC-6** An artefact whose inputs have changed since it was produced is never indexed as current.

#### FR-43 · The history of an output directory is visible
- **AC-1** Every invocation against an output directory is recorded with its command, its outcome (FR-45 AC-1),
  the invocation whose output it built on, the outputs it produced, and the outputs it superseded.
- **AC-2** An interrupted invocation is distinguishable from one that finished and from one still running.
- **AC-3** The user can view this history without an external service.
- **Interface** `history`

#### FR-28 · Each field of every artefact schema is documented as deterministic or not

### 5.5 Rendering

#### FR-3 · Render the knowledge graph into idiomatic TypeScript/NestJS source
- **AC-1** The rendered project runs from a clean checkout under its default configuration, without
  manual repair.
- **AC-2** Each source class maps to an identifiable unit of the output, so source and output can be
  compared side by side.
- **AC-3** The rendered source is written to a location the user chooses, or to a documented default.
- **AC-4** The rendered source is idiomatic for its target stack (§3).
- **Interface** `--source-out`

#### FR-4 · Render the knowledge graph into idiomatic Go source
A second target rendered from the same graph shows the graph is target-independent.
- **AC-1** FR-3's acceptance criteria apply, read against Go and its ecosystem conventions.

#### FR-5 · The render target is selectable at invocation, without a code change
- **AC-1** The set of available targets is discoverable at runtime.
- **AC-2** An unknown target fails before pipeline work begins.
- **Interface** `--target <name>`

#### FR-13 · Rendering output is capped per domain
Bounds LLM spend per render.
- **AC-1** A default cap applies when none is given, and its value is documented.
- **AC-2** The user can disable the cap, so every class in a domain is rendered.
- **AC-3** Selection at the cap is deterministic and documented (FR-14).
- **AC-4** The cap binding is reported to the user at the end of the invocation, naming the affected
  domains, so a capped rendering is never mistaken for a complete one.
- **Interface** `--max-classes-per-domain <n>`

#### FR-14 · Selection under the cap is deterministic and documented
- **AC-1** The same corpus and cap select the same classes every time, within the execution envelope.
- **AC-2** The ordering rule is documented. Where it uses thresholds, each cites a published source.
- **AC-3** The selection is auditable — what was selected, what was skipped, and by which rule.
- **AC-4** The partition of the corpus into domains is computed deterministically from the graph.

#### FR-36 · No source feature is ever silently dropped from rendered source
**Negative guarantee.** Anything the renderer cannot translate faithfully is visible in the output.
- **AC-1** An untranslatable feature surfaces as a reviewable placeholder carrying the original
  intent.
- **AC-2** Security-relevant features default to refusal, so a rendered endpoint is never silently
  less protected than its source.
- **AC-3** The encounter behaviour is configurable, and the permissive setting warns loudly.
- **AC-4** For each render target, the features it translates, defers, and refuses are documented in a
  single matrix.

#### NFR-5 · Adding a render target changes no shared code
- **AC-1** Adding a render target changes no code outside that target's own — not the analyzer, the core
  pipeline, the evaluation framework, or the command line.
- **AC-2** The documentation describes every step of adding a render target.

### 5.6 Evaluation

#### FR-7 · Run code-quality evaluations per target and produce target-specific scorecards
- **AC-1** The rendered source is compile-checked with the target stack's own toolchain.
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
tool's own output. Unlike FR-7c, which detects drift against a baseline captured from the tool, this
measures correctness: a tool can be stable and consistently wrong.
- **AC-1** For at least one corpus, an expectation of the graph's contents is authored from the source
  and confirmed by a person, independently of what the tool emits.
- **AC-2** The expectation is never regenerated from tool output — capture would record the tool's own
  errors as correct.
- **AC-3** The expectation may be partial. Which entries have been confirmed is recorded, and accuracy
  is reported only over the confirmed set.
- **AC-4** Runs are compared against it, and every difference is classified as improvement, regression,
  or intentional change.
- **AC-5** The expectation covers both what deterministic extraction should find and what enrichment
  should conclude. The semantic comparison is tolerance-based, not exact.

#### FR-18 · A scorecard over LLM-derived output records the exact model version that produced it
Exact version strings, never family names — so a score that moves can be attributed to the tool or to
the model.
- **AC-1** Where the artefact being scored was produced by an LLM, the scorecard records the model
  version and the prompt version (FR-15) that produced it.
- **AC-2** Where the artefact was produced deterministically, no model provenance is recorded, and its
  absence is not a gap.

#### FR-9 · Ship at least one complete example run per target, with committed output and scorecards
- **AC-1** The committed example includes the run's own output artefacts.
- **AC-2** It includes the graph scorecard and the target scorecard.
- **AC-3** For a render target, it includes the rendered source.
- **AC-4** Example output is illustrative, not a byte-equal regression golden (FR-7c).

#### FR-25 · An LLM-judge calibration suite discriminates known-good from known-bad output at documented thresholds, committed as a calibration record

#### NFR-3 · Evaluation results are reproducible
A past score can be re-derived by scoring the same artefact again.
- **AC-1** A scorecard records every input that determines its scores — the scored artefact's identity,
  the tool version, and for an LLM-judged score the judge's model and prompt versions.
- **AC-2** A deterministic check re-derives exactly; an LLM-judged score re-derives within a documented
  tolerance.

### 5.7 LLM platform control

#### FR-8 · Provider and model are both selectable, and neither is allowlisted
Two independent axes: which provider runs the call, and which model it runs.
- **AC-1** The provider is selectable without a code change.
- **AC-2** A provider endpoint the tool does not name is reachable by configuration alone, if it speaks
  the OpenAI-compatible API.
- **AC-3** Any model id the provider accepts can be used; the tool restricts none.
- **AC-4** A different model can be configured for each stage that calls an LLM, each falling back to
  one default model.
- **Interface** `CODEOGRAPH_LLM_PROVIDER`

#### FR-15 · Prompts are versioned, and a released version never changes
A score or a cached response can be attributed only if the prompt behind it is identified exactly
(FR-17, FR-18).
- **AC-1** A released prompt version never changes; a change makes a new version with its own identity.
- **AC-2** Which prompt version each stage uses by default is declared in one place, so changing a
  default is a reviewable change.
- **AC-3** A prompt declares the inputs it requires, and a missing or unknown input fails before the
  call is made.

#### FR-16 · Every LLM call is recorded on the user's machine
- **AC-1** Each LLM request — answered by the provider, answered from the cache, or failed — is recorded
  with the run correlation identifier, provider, model, prompt version, input and output tokens, cost
  estimate, latency, timestamp, and which of the three it was.
- **AC-2** The records are machine-readable and can be inspected without an external service.
- **AC-3** The run manifest records the run's total calls, tokens and cost.

#### NFR-8 · The tool sends data only where the user directs it
**Negative guarantee.** Source code and run data leave the user's machine only for the services the user
chose.
- **AC-1** The tool sends data only to the LLM provider the user configured and to the git host of a
  supplied URL; it sends nothing to its maintainers.

#### FR-17 · LLM responses are reused only for identical requests
So a re-run neither pays twice nor gets a different LLM answer to the same question.
- **AC-1** A cached response is served only for a request identical in everything that can change the
  response.
- **AC-2** A request that differs only in what cannot change the response — the run, the corpus, the
  caller — is served from the cache.

#### FR-37 · The response cache is inspectable and user-managed
- **AC-1** The user can see the cache's size, entry count, and hit rate.
- **AC-2** The user can purge selectively — by age, by model, by prompt version, or entirely.
- **AC-3** A cache entry is removed only when the user asks.
- **AC-4** Cache growth is reported to the user.
- **AC-5** Removing cache entries follows the consent rule of FR-45 AC-3 and AC-4.

#### FR-39 · LLM spend is bounded before and during every invocation that calls an LLM
**Negative guarantee.** No invocation can start unbounded paid LLM work.
- **AC-1** Before any paid work begins, an estimate of call count and cost is shown, stating the prices
  it is based on and their date; it is labelled an estimate, not a quote.
- **AC-2** Above a configurable call-count threshold, an interactive invocation asks for confirmation.
- **AC-3** A non-interactive invocation handles that confirmation as FR-45 AC-4 requires: it never waits
  for it and never proceeds without it.
- **AC-4** Optional hard ceilings on total calls and total tokens abort the invocation mid-flight,
  reporting what was completed.
- **AC-5** A dry run estimates cost without making paid calls.
- **AC-6** A ceiling on spend in money stops the invocation on projected or accumulated spend.
- **AC-7** At the end of each invocation that calls an LLM, its token use and cost are reported to the
  user.
- **Interface** `--max-llm-calls`, `--max-tokens-total`, `--llm-call-confirm-threshold`, `--yes`,
  `--non-interactive`, `--dry-run`, `--max-cost-usd`

#### NFR-2 · Input shared by many LLM calls is not paid for in full on every call
- **AC-1** Where the provider offers a reduced rate for repeated input, input shared by many calls is
  sent so that it qualifies.

### 5.8 Configuration and run safety

#### FR-38 · Configuration is layered, with an explicit and predictable precedence
Settings come from several places; which one wins is fixed and documented, so the same setup always
gives the same configuration.
- **AC-1** Settings resolve in a documented order: invocation flags, then environment variables, then
  the user's environment file, then the user's config file, then built-in defaults.
- **AC-2** Configuration is validated before any work begins.
- **AC-3** Secrets are read only from environment variables and the environment file — never from the
  config file or the command line.
- **AC-4** Every setting and credential the user can set is documented, with its default.
- **AC-5** No credential is written to any artefact, diagnostic record or console output, including one
  embedded in a git URL given as the source (FR-29 AC-2).
- **AC-6** The environment file and the config file are read from documented locations; no file in the
  source being analysed is read as configuration.

#### FR-27 · Writing output never damages content the tool did not produce
**Negative guarantee.** Content the tool did not produce is never lost to an invocation.
- **AC-1** All artefacts are written inside the output directory, except the rendered source, which is
  written where FR-3 AC-3 places it.
- **AC-2** An output directory that is the working directory, or an ancestor of it, is rejected.
- **AC-3** Re-running against a previous run's output directory needs no extra option, except as AC-6
  provides.
- **AC-4** Content the tool did not produce is removed only when the user asks.
- **AC-5** Content the tool did not produce is replaced only where its path matches a file the
  invocation would write, only when the invocation names that intent, and the replaced content is
  preserved (FR-42).
- **AC-6** An output directory written by an incompatible earlier version is never modified; the
  invocation is refused with a message stating how to proceed.
- **AC-7** The location of the rendered source holds nothing the tool writes except the rendered source.
- **Interface** `--on-existing`

#### FR-42 · Superseded output is preserved, not overwritten
**Negative guarantee.** No invocation destroys an earlier result.
- **AC-1** Output that a later invocation supersedes is preserved.
- **AC-2** Preserved output is removed only when the user asks.
- **AC-3** The user can remove preserved output selectively — by age, by count, or entirely.
- **AC-6** The growth of preserved output is reported to the user.
- **AC-7** Removing preserved output follows the consent rule of FR-45 AC-3 and AC-4.
- **Interface** `purge`

#### FR-44 · Concurrent invocations never corrupt their outputs
**Negative guarantee.** No two invocations can leave an output half one and half the other.
- **AC-1** Invocations that write disjoint outputs can run at the same time.
- **AC-2** An invocation that would write an output another running invocation is writing is refused.
- **AC-3** An invocation whose inputs change while it runs does not publish outputs built from the
  superseded inputs.
- **AC-4** An interrupted invocation never leaves a partially written output indexed as complete.
- **AC-5** A claim left by an invocation that is no longer running never blocks later invocations
  permanently; overriding one that may still be live needs consent (FR-45).

#### FR-45 · Every invocation's outcome is distinguishable, and risky operations need consent
- **AC-1** Success, failure, completion with recorded failures, completion with a failed quality check,
  refusal, and interruption are reported to the caller as distinct exit statuses.
- **AC-2** A refused invocation changes nothing except the diagnostic record of the refusal.
- **AC-3** An operation that cannot be undone, or that can disrupt another running invocation, happens
  only with explicit consent.
- **AC-4** A non-interactive invocation never waits for that consent and never proceeds without it.
- **Interface** `--yes`

#### FR-26 · Instructions planted in the analysed source are treated as data
Source text, and LLM output derived from it, reaches each later LLM call as data. No defence makes a
model immune, so injection is mitigated and the remaining risk is documented.

#### FR-46 · LLM output never decides where the tool writes, what it runs, or where it sends data
**Negative guarantee.** An instruction planted in the source can corrupt content, but cannot make the
tool act.
- **AC-1** File paths, executed commands and network destinations come from the graph, the configuration
  and the user's input — never from LLM output.

### 5.9 Engineering assurance

#### FR-19 · A test suite covers unit and integration behaviour
- **AC-1** Unit and integration layers are separated and independently runnable.
- **AC-2** Coverage below 80% fails the build.
- **AC-3** No test requires a live LLM provider or network access.
- **AC-4** Each failure class in FR-24 has a test asserting its error.

#### FR-7c · The knowledge graph is regression-tested against committed goldens
Goldens catch drift — any change in the graph for a fixed input; whether the graph is right is FR-41's.
- **AC-1** A golden is committed for a hand-built edge-case fixture corpus.
- **AC-2** A golden is committed for a pinned real-world project.
- **AC-3** On every CI run, the graph produced for each golden corpus equals its golden byte for byte in
  canonical form.
- **AC-4** A golden changes only through an explicit refresh step; an ordinary test run never writes
  one, and a missing golden fails the test.
- **AC-5** Each refresh records why the graph changed.
- **Interface** `pytest --update-goldens`

#### FR-23 · Rendered source is byte-stable for a fixed input
With the LLM responses held constant (FR-17), re-rendering the same graph produces identical bytes, and a
change in rendered output for unchanged inputs fails CI.

#### FR-21 · Secrets are caught before they reach the public repository
- **AC-1** A secret scan runs on every push and every pull request.
- **AC-2** A detection blocks the merge, with no maintainer bypass.
- **AC-3** Every place the scanner runs uses one exactly pinned version, and a check fails when they
  differ.
- **AC-4** A full-history scan runs on a schedule, independently of per-commit scanning.

#### NFR-4 · CI checks every change before it merges
- **AC-1** Lint, the test suite (FR-19), the evaluation of each committed example corpus, and the secret
  scan (FR-21) must pass before a change merges, with no bypass.
- **AC-2** Each committed example corpus is run and evaluated in CI, and its scorecards are kept as a
  downloadable record of the run.
- **AC-3** That evaluation exercises each shipped render target's own toolchain.

#### NFR-6 · The deterministic artefacts are byte-reproducible
Re-running the tool on the same corpus, with the same version and the same recorded extraction
settings, within the declared execution envelope (AC-4), produces byte-identical deterministic
artefacts.
- **AC-1** A single canonical form (§3) governs those artefacts.
- **AC-2** The canonical bytes are what is hashed for integrity (FR-33 AC-3), so one mechanism serves
  both comparison and integrity.
- **AC-3** No machine-specific value — absolute path, timestamp, locale, or iteration order — reaches
  a deterministic artefact.
- **AC-4** The execution envelope under which byte-equality holds is declared and pinned. Drift from it
  is detected and the comparison is skipped with a reason, never reported as a difference in output.

#### NFR-7 · Artefact schema versions are governed independently of the application version
Consumers pin the format, not the tool.
- **AC-1** Every emitted artefact whose format the tool defines declares its schema version in the
  artefact itself and in the manifest, independently per artefact.
- **AC-2** Artefact schema versions and the application version are separate version lines; neither
  implies the other.
- **AC-3** Within a major schema line, evolution is additive, so an existing consumer keeps working; a
  breaking change starts a new major line.

---

## 6. Retired identifiers

- **FR-6** — **Retired.** Its obligation is carried by NFR-5. The number is retained so existing
  references resolve.
- **NFR-1** — **Retired.** No longer tracked as a requirement. The number is retained so existing
  references resolve.

---

## 7. Status

This table records what ships today. `shipped` · `partial` · `planned` · `retired`.

A requirement targeted at a future release may carry no acceptance criteria; its criteria are written
when the design that satisfies it is decided. A `shipped` or `partial` requirement must carry criteria —
this table cites them by number, and a status of `partial` is not expressible without them.

**Rows whose note begins *Re-verify*** carry the status recorded before the acceptance criteria were
reworked in the 2026-08-23 re-specification. They have not yet been traced against the current
criteria: a `shipped` there is an unconfirmed claim, and an AC number its note cites may predate the
rework. Every other `shipped` or `partial` row has been traced to the code against the current criteria.

| ID | Status | Target | Note |
|---|---|---|---|
| FR-1 | shipped | v1 | Maven and Gradle both accepted; the build system is recorded per module. Neither gets classpath resolution: no symbol solver is configured in the parser, so method-call resolution is a source-only heuristic for both |
| FR-2 | shipped | v1 | |
| FR-3 | partial | v1 | AC-2 holds — per-class render granularity plus a deterministic project scaffold; full method bodies, not skeletons. AC-1 is not yet verified — the compile check runs the type-checker only, and no check installs or starts the rendered app. AC-3 holds — the user chooses `render`'s output location (it is required today; a documented default arrives with the output-layout change) |
| FR-4 | planned | v1.1 | |
| FR-5 | partial | v1 | AC-1 holds — `--list-targets` on `render` enumerates the registered targets. **AC-2 not met** — an unknown `--target` is rejected only after the input artefacts are loaded, `render`'s `--out` directory is cleared (under `--force`), a telemetry file is opened, and the LLM provider is constructed |
| FR-6 | retired | v1 | Retired 2026-08-23. Clause 1 (*a common renderer interface*) was ADR-008's mechanism, not an obligation; clause 2 (*no target-specific code in the core pipeline*) duplicated **NFR-5**, which carries it with acceptance criteria |
| FR-7 | partial | v1 | **AC-1 not met** — the compile check reads the manifest's `1.x` nested location for its sidecar pointer, which the `2.0.0` schema moved to a top-level peer, so it returns `skip` regardless of whether a render happened; its sidecar path also resolves against the run directory while the file is written to the render directory. AC-2 skips pending the render-time producer for its input. AC-3 llm_judge deferred |
| FR-7a | partial | v1 | **Re-verify.** **The statement's seven-check list is not fully met** — six of seven run; `semantic_accuracy` returns an explicit skip pending judge calibration, which is AC-2's permitted form, so no AC is breached. Separately, `structural_completeness` runs but its ground-truth source is an open question — a completeness ratio can only count declarations the extractor produced, so a declaration it never saw is absent from both sides. FR-41 is the intended oracle |
| FR-7b | partial | v1 | AC-3 holds — both schemas are committed. Graph half of AC-1 and AC-2 holds — the Pass-0 graph is built through the schema-generated model, and the graph scorecard re-validates it. **AC-1 not met for annotations** — they are written from a hand-written model, the schema-generated annotations model is never imported, and real annotation files fail the published schema at the root (the file is a list; the schema requires an object). **AC-2 not met for annotations** — the scorecard's validity check covers the graph only |
| FR-7c | shipped | v1 | **Re-verify.** AC-1 and AC-3 hold — the hand-built fixture corpus golden is committed and CI-gated byte-equal. **AC-2 is correctly deferred**, not missing: the real-project corpus and its golden were moved to v1.1 by design, and the fixture golden satisfies the v1 drift guardrail. AC-4 and AC-5 are obligations on the refresh procedure and are not separately verified here |
| FR-8 | shipped | v1 | **Re-verify.** `anthropic`, `openrouter`, `openai_compatible` live; `ollama` and `bedrock` wired in the resolver but raise `NotImplementedError`. Per-stage overrides present; no curated differential mapping |
| FR-9 | partial | v1 | **Re-verify.** **AC-1 and AC-3 not met; AC-2 partially met** — two committed example corpora ship a graph scorecard each; no committed run output, target scorecard, or rendered source. AC-4 holds |
| FR-10 | shipped | v1 | |
| FR-11 | shipped | v1 | |
| FR-12 | shipped | v1 | Cyclomatic, cognitive, WMC, CBO, LCOM4, MLOC — each cited; null where not computable |
| FR-13 | partial | v1 | AC-1 holds — default 3, documented in the user guide. **AC-2 not met** — `0` is rejected rather than disabling the cap. **AC-3 not met** — see FR-14. **AC-4 not met** — nothing reports the cap binding at the end of a render; the user guide itself says classes beyond the cap are *"silently excluded"* |
| FR-14 | partial | v1 | AC-1 and AC-4 hold — selection and the domain partition are pure functions of the graph. **AC-2 not met** — the thresholds are cited, but the documented ordering rule (ADR-009: a composite of CBO and WMC) is not the one implemented (WMC alone). **AC-3 not met** — no record of what was selected or skipped is persisted. Only the strategy name reaches the output, in a generated module's header comment, beside a "selected" count that is the group's total |
| FR-15 | partial | v1 | **Re-verify.** Versioned prompt files with content-hash pinning ship. **AC-3 not verified** — the prompt input-contract check is not separately confirmed. *(The scorecard `prompt_id` gap moved to FR-18 AC-1, which owns provenance.)* |
| FR-16 | partial | v1 | **AC-1 not met** — cost estimate is hardcoded `0.0`; the field exists, the value is never computed. AC-2 and AC-3 hold: all other fields are emitted to the sidecar JSONL and aggregates roll into the manifest |
| FR-17 | shipped | v1 | **Re-verify.** SQLite content-addressed store; key covers all response-affecting inputs |
| FR-18 | partial | v1 | **Re-verify.** AC-2 holds — the graph scorecard records no model provenance, correctly, since its subject is deterministic. **AC-1 unmet**: the code scorecard grades LLM-rendered source and its `model_version` / `prompt_id` fields, present in both the model and the published schema, are never populated |
| FR-19 | shipped | v1 | **Re-verify.** `--cov-fail-under=80` enforced in CI; mock provider, no live calls |
| FR-20 | shipped | v1 | `manifest.json` + `logs.jsonl` in the output directory; `run_id` correlates; dual-channel emission with `-v`/`-q`/`--log-level` |
| FR-21 | shipped | v1 | **Re-verify.** Exact-pinned gitleaks in CI with a parity check and a nightly full-history scan; no admin bypass |
| FR-22 | planned | v1.1 | FR-39's call-and-token floor stands in for v1; FR-39 is retired when this lands |
| FR-23 | planned | v1.1 | |
| FR-24 | planned | v1.1 | |
| FR-25 | planned | v1.1 | |
| FR-26 | planned | v1.1 | |
| FR-27 | partial | v1 | **AC-1 not met** — `render` writes the compile-check file under its own `--out`, outside the run's output directory; telemetry, also written outside it, is a diagnostic record rather than an artefact (§3). AC-2's cwd-or-ancestor rejection is verified. AC-5 holds today only incidentally: nothing is overwritten without `--force`, which is consent given at invocation. **AC-4 not met** — with `--force`, `render` clears its `--out` directory entirely, deleting content the tool did not produce. **AC-3 not met** — a re-run against a previous run's output is refused unless `--force` is given. **AC-6 not met** — an output directory from an incompatible earlier version is not detected. |
| FR-28 | planned | v1.1 | |
| FR-29 | shipped | v1 | Local, git, and zip acquirers all present |
| FR-30 | partial | v1 | AC-1, AC-2 and AC-3 hold — multi-module enumeration with module labelling, ignore-rule-driven exclusion, `.java`-only parsing. **AC-4 not met** — the Kotlin source root is dropped silently, with no log, warning, or record in the run's output |
| FR-31 | partial | v1 | AC-1, AC-2 and AC-4 hold — the AST → regex → name-only stub ladder runs, the run continues on parser failure, and each degraded file records its extraction mode. **AC-3 not met** — fallback is logged per file (`parser/file_parser_dispatcher.py:74`); no run-level report names the affected files, which is what ADR-003's amendment specifies |
| FR-32 | partial | v1 | AC-2 and AC-4 hold — 38 interpreted annotations are documented, and Lombok members are synthesised in the parser. **AC-1 not met in one case** — annotation-type declarations carry no annotations, so meta-annotations such as `@Retention` on a custom annotation are not captured. **AC-3 not met** — the documented criterion (*"interpreted when it lifts to a structured graph field or edge"*) is stated in terms of its own outcome |
| FR-33 | partial | v1 | AC-4 holds — skipped LLM passes are signalled by an explicit flag, not a null hash. **AC-3 and AC-5 not met on LLM-enabled runs** — the graph's recorded SHA-256 is of the graph as first written; enrichment then rewrites the file, so the hash no longer matches what is on disk and an integrity check reports the tool's own output as modified (see FR-34). **AC-1 not met** — the rendered source is an artefact (§3) and is not indexed; the manifest's `artefacts` map holds only the graph and the annotations. **AC-2 not met** — a re-run resets the scorecard and compile-check pointer maps. **AC-6 not met** — nothing records an artefact's inputs, so an artefact built from changed inputs stays indexed as current |
| FR-34 | partial | v1 | Holds when enrichment is disabled. **AC-1, AC-3 and AC-4 not met on LLM-enabled runs** — the corpus-synthesis pass writes four LLM-derived fields (`projectOverview`: description, architecture pattern, domains, cross-domain dependencies) into the graph and rewrites the file without the canonical form. The deterministic graph then differs from an enrichment-disabled run and cannot be obtained on its own. The graph schema declares the field; no design record decides it. AC-2 holds — no call outcome is recorded in the graph |
| FR-35 | partial | v1 | AC-2 to AC-7 hold — per-node annotation failures are logged and the node marked un-enriched (the annotation record's `degraded` flag), oversized inputs fall back to signatures with the reduction recorded, a failure ratio above the configured maximum aborts loudly, and the pipeline runs with LLM passes off. **AC-1 not met for corpus synthesis** — it is a single call, and its failure aborts the whole run, discarding the per-node annotations already produced |
| FR-36 | partial | v1 | AC-4 holds as documentation — ADR-010 Fork 9 is the matrix — but the code enforces only two of its refuse rows (Security, WebFlux); classes in the other refuse rows are rendered. **AC-1 not met** — a class refused by policy, or whose render call fails, is absent from the output with no placeholder, and a refusal is logged at debug level only. Placeholders inside a rendered class are asked for in the prompt, not enforced. **AC-2 not met for method-level security** — the policy checks class-level annotations only, so a controller secured by `@PreAuthorize` on its methods is rendered with no refusal and no guard stub. **AC-3 not met** — no user-reachable setting changes any policy: `render` builds the renderer's configuration from three CLI flags and reads no configuration section, and the permissive values carry no warning |
| FR-37 | shipped | v1 | **Re-verify.** `cache stats`, `cache purge` (dry-run by default), `cache report` |
| FR-38 | partial | v1 | **Re-verify.** Precedence documented in the committed config file and enforced by the settings layer. **AC-5 not yet verified** — whether a credential embedded in a git URL can reach the run log is untraced |
| FR-39 | shipped | v1 | **Re-verify.** Pre-flight estimate from a dated local price table, TTY-aware confirmation gate, and mid-run call/token ceilings |
| NFR-1 | retired | — | Number retained so existing references resolve |
| NFR-2 | partial | v1 | **Re-verify.** Prefix caching ships. AC-2 token and cost scorecard not shipped, and blocked behind FR-16's uncomputed cost |
| NFR-3 | partial | v1 | **Re-verify.** AC-1 holds — the scorecard carries `seed`. **AC-2 not met** — the provenance FR-18 requires is unpopulated, so a past LLM-derived score cannot be re-derived; same root cause as FR-18 AC-1 |
| NFR-4 | partial | v1 | **Re-verify.** Lint, unit tests, and a per-corpus eval job all run. AC-3 not yet met — the eval job runs the deterministic path and does not invoke the target toolchain |
| NFR-5 | partial | v1 | The architecture holds — a renderer is a self-contained package behind a registry. **AC-1 not met** — `Scorecard.kind` is a hardcoded `Literal["graph","ts","go"]`, so a new target also requires editing the eval model. **AC-2 not met** — the renderer-authoring section is not yet written. Also, the render pipeline hardcodes the TypeScript renderer's prompt directory and prompt id when it builds the render cache key, and the CLI imports the TypeScript package by name to register it — so a second target would also edit the core pipeline and the CLI, and until then its cache key would hash the TypeScript prompt |
| FR-40 | partial | v1 | AC-1 and AC-2 hold — unresolvable calls are emitted as `calls_unresolved`, and an unresolved edge is replaced only by a resolved one, never dropped. **AC-3 not met** — nothing reports conditions that reduce resolution to the user. The remediation hint the status once cited does not exist, and the symbol solver that would consult a local Maven repository is not configured: resolution is a four-case source-only heuristic, and local-variable callees always stay unresolved. AC-4 has nothing to act on while AC-3 is unmet |
| FR-41 | planned | v1.1 | Not shipped in any form. FR-7c's harness detects drift against a captured baseline, which cannot serve as a correctness oracle. The two accuracy checks that need this expectation are `structural_completeness` (its ground-truth source is an open question) and `semantic_accuracy` (skipped, deferred) |
| FR-42 | planned | v1 | |
| FR-43 | planned | v1 | |
| FR-44 | planned | v1 | |
| FR-45 | planned | v1 | |
| NFR-6 | partial | v1 | Holds when enrichment is disabled — canonical serialisation in the writer, and the same bytes feed the manifest hash and the golden assertion. **AC-1 and AC-2 not met on LLM-enabled runs** — the corpus-synthesis pass rewrites the graph without the canonical form, so the file on disk is neither canonical nor the bytes that were hashed (see FR-34). Goldens are captured without enrichment, so they never see this |
| NFR-7 | shipped | v1 | **Re-verify.** Graph and manifest schema versions are independent of the application version; manifest is `2.0.0`, strict-additive within `2.x` |

---

## 8. Revision history

The first set of these requirements was drafted before implementation began, and revised during design
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
