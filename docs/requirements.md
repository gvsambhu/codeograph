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
added to this repository as this document on 2026-08-06, after the first implementation was built. Requirements
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
| **Deterministic artefact** | The class of artefacts FR-34 and NFR-6 constrain. The knowledge graph is the only one. |
| **Canonical form** | The single byte-level serialisation rule for an artefact (key ordering, separators, encoding, line ending) that makes byte-comparison and hashing meaningful. |
| **Execution envelope** | The declared, pinned environment within which byte-level reproducibility holds (NFR-6 AC-4). Determinism claims elsewhere in this document are made within it. |
| **Golden** | A committed known-good artefact for a pinned input (FR-7c). |
| **Diagnostic record** | A file the tool writes for later inspection rather than as an output — the structured run log, the LLM call records (FR-16), and the invocation history (FR-43). Not an artefact. |
| **Prompt** | The instruction text the tool sends to an LLM with each call. It ships with the tool; it is not an artefact. |
| **Spend** | The LLM usage an invocation incurs — its calls, its tokens or its cost. |
| **Domain** | A grouping of classes used to partition the corpus for rendering (FR-14). |
| **Render target** | A language/framework stack the graph can be rendered into (FR-3, FR-4, NFR-5). |
| **Rendered project** | The rendered source together with the files that build and run it in its target stack. |
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
Each class below fails with the failure outcome (FR-45 AC-1) and an error naming the cause; at minimum:
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
- **AC-6** Past a defined threshold of enrichment failures, the run ends with the failure outcome
  (FR-45 AC-1).
- **AC-7** A run can be performed with enrichment disabled, producing the deterministic artefacts
  alone.

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
- **AC-3** Each schema is committed to the repository, so an external consumer can validate output
  without importing the producing package.

#### FR-20 · Every run writes a manifest and a structured run log
- **AC-1** A run manifest is written into the output directory as the entry point to the run.
- **AC-2** A structured, machine-readable run log is written into the output directory for the same run.
- **AC-3** A run correlation identifier joins the manifest, the structured run log, and the LLM call
  records (FR-16).
- **AC-4** Human-readable console output and the structured run log are emitted together; verbosity
  is controllable at invocation.

#### FR-33 · The manifest is an integrity contract over the run's artefacts
- **AC-1** The manifest indexes every artefact produced by an invocation against the output directory
  that has not since been superseded, including a rendered source written outside it, except the
  manifest itself, which is the index.
- **AC-2** Pointers to artefacts produced by an earlier invocation against the same directory are
  retained when a later invocation rewrites the manifest, unless the later invocation supersedes them.
- **AC-3** Each indexed artefact carries a cryptographic hash of its bytes as written.
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
- **AC-2** An unknown target fails before any work begins.
- **Interface** `--target <name>`

#### FR-13 · Rendering is capped per domain
Bounds LLM spend per render.
- **AC-1** A default cap applies when none is given, and its value is documented.
- **AC-2** The user can disable the cap, so every class in a domain is rendered.
- **AC-3** Selection at the cap is deterministic and documented (FR-14).
- **AC-4** When the cap leaves classes out, the user is told at the end of the invocation, with the
  domains affected, so a capped rendering is never mistaken for a complete one.
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
- **AC-3** How an untranslatable feature is treated is configurable.
- **AC-4** For each render target, the features it translates, defers, and refuses are documented in a
  single matrix.
- **AC-5** An invocation using a setting that weakens AC-1 or AC-2 warns the user.

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
- **AC-4** Runs are compared against it, and every difference is classified, into documented categories
  that separate a regression from an intended change.
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
- **AC-3** Each invocation that called an LLM records its total calls, tokens and cost, inspectable
  without an external service.

#### NFR-8 · The tool sends data only where the user directs it
**Negative guarantee.** Source code leaves the user's machine only for the service the user chose.
- **AC-1** Source code, and data derived from it, are sent only to the LLM provider the user configured;
  nothing is sent to the tool's maintainers.

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
- **AC-4** Optional hard ceilings on spend abort the invocation mid-flight, reporting what was completed.
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
**Negative guarantee.** Content the tool did not produce is never lost to an invocation, except by a
removal the user asks for.
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
- **AC-7** A rendered project contains no other artefact or diagnostic record of the tool.
- **Interface** `--on-existing`

#### FR-42 · Superseded output is preserved, not overwritten
**Negative guarantee.** No invocation destroys an earlier result unless the user asks it to.
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
- **AC-5** An invocation that stopped without finishing never blocks later invocations permanently;
  taking over from one that may still be running needs consent (FR-45 AC-3).

#### FR-45 · Every invocation's outcome is distinguishable, and risky operations need consent
- **AC-1** Success, failure, completion with recorded failures, completion with a failed quality check,
  refusal, and interruption are reported to the caller as distinct exit statuses.
- **AC-2** A refused invocation changes nothing except the diagnostic record of the refusal.
- **AC-3** A removal that cannot be undone, or an operation that can disrupt another running
  invocation, happens only with explicit consent.
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
change in the rendered source for unchanged inputs fails CI.

#### FR-21 · Secrets are caught before they reach the public repository
- **AC-1** A secret scan runs on every push and every pull request.
- **AC-2** A detection fails the scan, so the change cannot merge (NFR-4 AC-1).
- **AC-3** Every place the scanner runs uses one exactly pinned version, and a check fails when they
  differ.
- **AC-4** A scan of the full history of every branch on the public repository runs on a schedule,
  independently of per-commit scanning.

#### NFR-4 · CI checks every change before it merges
- **AC-1** Lint, the test suite (FR-19), the evaluation of each committed example corpus, and the secret
  scan (FR-21) must pass before a change merges, with no bypass.
- **AC-2** Each committed example corpus is run and evaluated in CI, and its scorecards are kept as a
  downloadable record of the run.
- **AC-3** That evaluation exercises each render target's own toolchain.

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
- **FR-22** — **Retired.** Its criteria — a dry run, and a spend ceiling in money — are carried by FR-39
  (AC-5, AC-6). The number is retained so existing references resolve.

---

## 7. Status

This table records what ships today. `shipped` · `partial` · `planned` · `retired`. *Shipped* means
merged to `main`; no release has been tagged yet. *Scope* is the [roadmap](../ROADMAP.md) scope that owns
the requirement; a criterion owned by another scope is named beside it.

A `planned` requirement may carry no acceptance criteria; its criteria are written
when the design that satisfies it is decided. A `shipped` or `partial` requirement must carry criteria —
this table cites them by number, and a status of `partial` is not expressible without them.

**Rows whose note begins *Re-verify*** carry a status not yet traced against the current criteria —
recorded before the 2026-08-23 re-specification, or assigned when a requirement was added since. A
`shipped` there is an unconfirmed claim, and an AC number its note cites may predate the rework. Every other `shipped` or `partial` row has been traced to the code against the current criteria.

| ID | Status | Scope | Note |
|---|---|---|---|
| FR-1 | partial | SC-001 | AC-1 and AC-2 hold — Maven and Gradle both accepted. **AC-3 not met** — the build system is recorded per module during discovery, but no module node is ever built, so it never reaches the graph. Neither build system gets classpath resolution: no symbol solver is configured in the parser, so method-call resolution is a source-only heuristic for both. **AC-4 not met** — built-in exclusions (`target/`, `build/`, `out/`) apply at any depth beside the project's own ignore rules, so a source package with one of those names is dropped without a report, and only a project-specific ignore rule restores it (`input/source_discoverer.py:33`). Source roots are the conventional `src/main/java` and `src/test/java`; a source directory a build file declares elsewhere is not read either, and nothing reports it |
| FR-2 | shipped | SC-001 | |
| FR-3 | partial | SC-005 | AC-2 holds — per-class render granularity plus a deterministic project scaffold; full method bodies, not skeletons. AC-3 holds — the user chooses `render`'s output location (it is required today; a documented default arrives with the output-layout change). **AC-1 not yet verified** — the check that would install and type-check the rendered project is declared but never runs (FR-7 AC-1), and no check starts the app. **AC-4 not yet verified** — no check judges idiom yet (FR-7 AC-3 is deferred) |
| FR-4 | planned | SC-009 | |
| FR-5 | partial | SC-005 | AC-1 holds — `--list-targets` on `render` enumerates the registered targets. **AC-2 not met** — an unknown `--target` is rejected only after the input artefacts are loaded, `render`'s `--out` directory is cleared (under `--force`), a telemetry file is opened, and the LLM provider is constructed |
| FR-6 | retired | — | Retired 2026-08-23. Clause 1 (*a common renderer interface*) was ADR-008's mechanism, not an obligation; clause 2 (*no target-specific code in the core pipeline*) duplicated **NFR-5**, which carries it with acceptance criteria |
| FR-7 | partial | SC-006 | **AC-1 not met** — the compile check reads the manifest's `1.x` nested location for the compile-check record's pointer, which the `2.0.0` schema moved to a top-level peer, so it returns `skip` regardless of whether a render happened; that record's path also resolves against the run directory while the file is written to the render directory. AC-2 skips pending the render-time producer for its input. AC-3 llm_judge deferred |
| FR-7a | partial | SC-006 | AC-1 to AC-3 hold. **The statement's seven-check list is not fully met** — six of seven run; `semantic_accuracy` returns an explicit skip pending judge calibration, which is AC-2's permitted form, so no AC is breached, and `golden_graph_agreement` skips (`no_golden_committed`) for any corpus without a committed golden, which includes both committed example corpora. Separately, `structural_completeness` runs as a ratio of declarations the extractor produced, so a declaration it never saw is absent from both sides; ADR-032 (proposed) redefines it against FR-41's expectation; and `internal_consistency` enforces four of the five invariants its rationale names |
| FR-7b | partial | SC-002 | AC-3 holds — both schemas are committed. Graph half of AC-1 and AC-2 holds for the first write — the graph is built through the schema-generated model, and the graph scorecard re-validates it; on an LLM-enabled run the corpus-synthesis pass then rewrites `graph.json` from a plain dictionary without validating it. **AC-1 not met for the enrichment file** — it is written from a hand-written model, the schema-generated model for it is never imported, and real enrichment files (`llm-annotations.json`) fail the published schema at the root (the file is a list; the schema requires an object). **AC-2 not met for the enrichment file** — the scorecard's validity check covers the graph only |
| FR-7c | partial | SC-007 (AC-2: SC-010) | AC-1 and AC-4 hold — the hand-built fixture corpus golden is committed and CI-gated, goldens change only through `--update-goldens`, and a missing golden fails the test. **AC-2 not met** — the real-project golden is planned (SC-010). **AC-3 not met** — when the bytes differ, the test compares both sides re-indented as JSON, so a difference that leaves the parsed graph equal (whitespace, separators, a trailing newline) passes. **AC-5 not met** — nothing records why a refresh changed the graph |
| FR-8 | shipped | SC-003 | AC-1 to AC-4 hold — `anthropic`, `openrouter` and `openai_compatible` are selected by setting and each builds from configuration; each stage runs on its configured model, falling back to the default (`llm/providers/langchain_base.py`, a chat object per model); any model id is passed through. `ollama` and `bedrock` are wired in the resolver but raise `NotImplementedError` — not scheduled. No curated differential mapping |
| FR-9 | partial | SC-006 | **AC-1, AC-2 and AC-3 not met** — two committed example corpora ship a graph scorecard each (the graph half of AC-2); no committed run output, target scorecard, or rendered source. AC-4 holds |
| FR-10 | partial | SC-001 | AC-1 holds — no LLM call takes part in extraction. **AC-2 not met** — a file whose parser subprocess times out (30 seconds) or crashes falls back to the regex extractor with no retry, so the same corpus can yield different structural facts on two runs (`parser/java_file_parser.py:99`, `parser/file_parser_dispatcher.py:73`) |
| FR-11 | shipped | SC-003 | |
| FR-12 | partial | SC-001 | Cyclomatic, cognitive, WMC, CBO and LCOM4 each cite a published source; null where not computable. **AC-1 not met** — the method-line-count computation counts the declaration's whole line span, annotations included (`parser/java/src/main/java/io/codeograph/parser/ComplexityCalculator.java:161`), which matches neither the definition ADR-004 §3.6 gives nor the SonarSource rule it cites; the graph schema's description of the field matches neither. AC-2 to AC-4 hold |
| FR-13 | partial | SC-005 | AC-1 holds — default 3, documented in the user guide. **AC-2 not met** — the cap cannot be disabled (`0`, the documented value, is rejected). **AC-3 not met** — see FR-14. **AC-4 not met** — nothing reports the cap binding at the end of a render; the user guide itself says classes beyond the cap are *"silently excluded"* |
| FR-14 | partial | SC-005 | AC-1 and AC-4 hold — selection and the domain partition are pure functions of the graph. **AC-2 not met** — the thresholds are cited, but the documented ordering rule (ADR-009: a composite of CBO and WMC) is not the one implemented (WMC alone). **AC-3 not met** — no record of what was selected or skipped is persisted. Only the strategy name reaches the output, in a generated module's header comment, beside a "selected" count that is the group's total |
| FR-15 | partial | SC-004 | Versioned prompt files with content-hash pinning ship; a body edited without refreshing the pin is rejected at load. **AC-1 not met** — the pin is refreshed by a script that the pre-commit hook and CI run, so an edited body stays at its version, and nothing compares a prompt with a released copy (no release is tagged yet). **AC-2 not met** — the annotation and synthesis prompts declare their default version in `default.yaml`; the render prompt's version is hard-coded in the renderer and the render pipeline. **AC-3 not met** — a missing input fails before the call, an unknown one is ignored. *(The scorecard `prompt_id` gap is FR-18 AC-1's.)* |
| FR-16 | partial | SC-004 | AC-2 holds. **AC-1 not met** — every request is recorded, answered, cached or failed, but the cost estimate is a hardcoded `0.0`, and a failed request records the tier name instead of a model. **AC-3 not met** — `run`'s call and cache-hit counts roll into the manifest per pass, replaced by a later run; no tokens or cost are recorded there, and `render`'s calls are not recorded there at all; per-call cost in telemetry reads 0; no per-invocation record exists yet (FR-43 is planned) |
| FR-17 | partial | SC-004 | AC-2 holds. **AC-1 not met** — the cache key carries a provider label (the configured label, else the endpoint's host name) but not the endpoint URL, and the cache is shared by every run, so two endpoints on one host, or sharing a label, serve each other's entries; the key's model is the configured one, which per-stage calls do not use (FR-8 AC-4) |
| FR-18 | partial | SC-006 | AC-2 holds — the graph scorecard records no model provenance, correctly, since its subject is deterministic. **AC-1 unmet**: the code scorecard grades LLM-rendered source and its `model_version` / `prompt_id` fields, present in both the model and the published schema, are never populated |
| FR-19 | partial | SC-007 (AC-4: SC-013) | AC-1 to AC-3 hold — the unit and integration layers run separately (a partial run needs `--no-cov`); `--cov-fail-under=80` enforced in CI; mock provider, no live calls. **AC-4 not met** — the tests for FR-24's failure classes are planned (SC-013) |
| FR-20 | shipped | SC-001 | `manifest.json` + `logs.jsonl` in the output directory; `run_id` correlates; dual-channel emission with `-v`/`-q`/`--log-level` |
| FR-21 | shipped | SC-007 | **Re-verify** AC-4 only — the scheduled job fetches every branch and succeeds nightly; whether it scans branches other than `main` is not shown by its log. AC-1 to AC-3 hold — every pushed branch and every pull request is scanned (a tag push is not); the default branch's ruleset requires the scan, with no bypass; gitleaks is exact-pinned with a parity check |
| FR-22 | retired | — | Retired 2026-11-10. Folded into FR-39 (AC-5, AC-6), which is permanent |
| FR-23 | planned | SC-011 | |
| FR-24 | partial | SC-002 | **AC-1 and AC-2 not met** — see FR-29 AC-4. **AC-3 not met** — an extraction error other than a corrupt archive (an unsupported compression method, an encrypted entry) escapes without an error naming the cause. **AC-4 not met** — cloning a git URL that needs credentials can wait for input instead of failing. **AC-5 and AC-6 not met** — an empty corpus, and a directory with no build file, both finish with exit status 0, an empty graph and a manifest |
| FR-25 | planned | SC-010 | |
| FR-26 | planned | SC-013 | |
| FR-27 | partial | SC-008 | **AC-1 not met** — `render` writes the compile-check file under its own `--out`, outside the run's output directory; telemetry, also written outside it, is a diagnostic record rather than an artefact (§3). AC-2's cwd-or-ancestor rejection is verified. **AC-5 not met** — with `--force`, replaced content is deleted, not preserved (see AC-4). **AC-4 not met** — with `--force`, `render` clears its `--out` directory entirely, deleting content the tool did not produce. **AC-3 not met** — a re-run against a previous run's output is refused unless `--force` is given. **AC-6 not met** — an output directory from an incompatible earlier version is not detected. **AC-7 not met** — the same compile-check file sits in the rendered source's location |
| FR-28 | planned | SC-011 | |
| FR-29 | partial | SC-001 | AC-1, AC-2 and AC-3 hold — local, git and zip acquirers. AC-5 holds when acquisition succeeds — the temporary location is removed in the pipeline's `finally` block; **not met when zip extraction fails** with anything but a corrupt-archive error, which leaves the partly extracted folder behind (`input/acquirers/zip_acquirer.py:56`). **AC-4 not met** — zip extraction has no size cap, and an entry resolving outside the extraction root is rewritten into it by the extractor rather than rejected (`input/acquirers/zip_acquirer.py:57`; FR-24 AC-1, AC-2) |
| FR-30 | partial | SC-002 | AC-3 holds — `.java`-only parsing. **AC-1 not met** — modules are enumerated during discovery, and each type is labelled with its module by a `contains` edge, but the graph holds no module node, so the edges name a module that is not in it. **AC-2 not met** — only the corpus root's and each module root's ignore file is read; a nested one is not. **AC-4 not met** — the Kotlin source root is dropped silently, with no log, warning, or record in the run's output |
| FR-31 | partial | SC-002 | AC-1, AC-2 and AC-4 hold — the AST → regex → name-only stub ladder runs, the run continues on parser failure, and each degraded file records its extraction mode. **AC-3 not met** — fallback is logged per file (`parser/file_parser_dispatcher.py:74`); no run-level report names the affected files, which is what ADR-003's amendment specifies |
| FR-32 | partial | SC-002 | AC-2 and AC-4 hold — 38 interpreted annotations are documented, and Lombok members are synthesised in the parser. **AC-1 not met in one case** — annotation-type declarations carry no annotations, so meta-annotations such as `@Retention` on a custom annotation are not captured. **AC-3 not met** — the documented criterion (*"interpreted when it lifts to a structured graph field or edge"*) is stated in terms of its own outcome |
| FR-33 | partial | SC-002 | AC-4 holds — skipped enrichment is signalled by an explicit flag, not a null hash. **AC-1 not met** — the rendered source is an artefact (§3) and is not indexed; the manifest's `artefacts` map holds only the graph and the enrichment file, and the compile-check pointer's path resolves against the wrong directory. **AC-2 not met** — a re-run resets the scorecard and compile-check pointer maps, and `eval run` replaces the scorecard map with the kinds it just evaluated. **AC-3 and AC-5 not met** — on LLM-enabled runs the graph's recorded SHA-256 is of the graph as first written; enrichment then rewrites the file, so the hash no longer matches what is on disk and an integrity check reports the tool's own output as modified (see FR-34); the rendered source is not covered at all. **AC-6 not met** — nothing records an artefact's inputs, so an artefact built from changed inputs stays indexed as current |
| FR-34 | partial | SC-002 | Holds when enrichment is disabled. **AC-1, AC-3 and AC-4 not met on LLM-enabled runs** — the corpus-synthesis pass writes four LLM-derived fields (`projectOverview`: description, architecture pattern, domains, cross-domain dependencies) into the graph and rewrites the file without the canonical form. The knowledge graph then differs from an enrichment-disabled run and cannot be obtained on its own. The graph schema declares the field; no design record decides it. AC-2 holds — no call outcome is recorded in the graph |
| FR-35 | partial | SC-003 | AC-2 to AC-7 hold — per-node enrichment failures are logged and the node marked un-enriched (the enrichment record's `degraded` field), oversized inputs fall back to signatures with the reduction recorded, a failure ratio above the configured maximum aborts loudly, and the pipeline runs with enrichment disabled. **AC-1 not met for corpus synthesis** — it is a single call, and its failure ends the run before the manifest is written, leaving the per-node enrichment on disk, unindexed |
| FR-36 | partial | SC-005 | AC-4 holds as documentation — ADR-010 Fork 9 is the matrix — but the code enforces only two of its refuse rows (Security, WebFlux); classes in the other refuse rows are rendered. **AC-1 not met** — a class refused by policy, or whose render call fails, is absent from the output with no placeholder, and a refusal is logged at debug level only. Placeholders inside a rendered class are asked for in the prompt, not enforced. **AC-2 not met for method-level security** — the policy checks class-level annotations only, so a controller secured by `@PreAuthorize` on its methods is rendered with no refusal and no guard stub. **AC-3 not met** — no user-reachable setting changes any policy: `render` builds the renderer's configuration from three CLI flags and reads no configuration section. **AC-5 not met** — the permissive values carry no warning |
| FR-37 | partial | SC-004 | `cache stats` and `cache report` give size, entry count and hit rate; purge is selective and removes only on request. **AC-4 not met** — the configured size and entry limits are never read, so no growth is reported. AC-5 holds — `cache purge` is a dry run unless `--force`, a flag documented as performing the deletion; FR-45's consent flag (`--yes`) is a different name |
| FR-38 | partial | SC-004 | AC-1 and AC-4 hold — precedence is enforced by the settings layer; settings and credentials are documented in the repository's example files and user guide. **AC-2 not met** — `run` clears `--out` before validating, and `render` validates after clearing it and without a usage error. **AC-3 not met** — a key in `config.yaml` is read. AC-5 holds — a source location carrying a secret is refused before anything is written or echoed (`input/source_location.py`); git's error text carries none. **AC-6 not met** — the environment file and the config file are read from the current working directory, which can be the analysed project |
| FR-39 | partial | SC-004 (AC-5 to AC-7: SC-012) | A pre-flight estimate from a dated local price table, a TTY-aware confirmation gate and mid-run call and token ceilings exist for `run`. AC-2 holds. **AC-1 not met** — the estimate states a total and the price date but not the prices, and prices every stage on the default model. **AC-3 not met** — `--non-interactive` waives the confirmation instead of refusing. **AC-4 not met** — a ceiling is treated as a node failure in Pass 1, and the abort reports nothing of what completed. **Not met for `render`**, which shows no estimate, asks no confirmation, and takes no ceiling flags; a call or token ceiling set by environment variable or config file does apply to it. **AC-5, AC-6 and AC-7 not met** — planned (SC-012) |
| FR-40 | partial | SC-002 | AC-4 has nothing to act on while AC-3 is unmet. **AC-1 not met** — calls the tool cannot resolve are emitted as `calls_unresolved` and replaced only by a resolved edge, never dropped; but a type reference outside the file's explicit imports (a same-package class, a wildcard import, a library type) yields no edge and no unresolved marker. **AC-3 not met** — nothing reports conditions that reduce resolution to the user. The remediation hint the status once cited does not exist, and the symbol solver that would consult a local Maven repository is not configured: resolution is a four-case source-only heuristic, and local-variable callees always stay unresolved |
| FR-41 | planned | SC-010 | Not shipped in any form. FR-7c's harness detects drift against a captured baseline, which cannot serve as a correctness oracle. The two accuracy checks that need this expectation are `structural_completeness` (ADR-032, proposed, defines it against this expectation) and `semantic_accuracy` (skipped, deferred) |
| FR-42 | planned | SC-008 | |
| FR-43 | planned | SC-008 | |
| FR-44 | planned | SC-008 | |
| FR-45 | planned | SC-008 | |
| FR-46 | shipped | SC-004 | AC-1 holds — rendered file paths come from the graph's package and class names or the user's configuration; the compile-check commands are fixed by the renderer; network destinations come from settings |
| NFR-1 | retired | — | Number retained so existing references resolve |
| NFR-2 | partial | SC-003 | **AC-1 not met** — the cache hint is placed in a message's `additional_kwargs`, which `ChatAnthropic` ignores, so no Anthropic request carries a cache marker; for OpenAI-compatible endpoints no cache marker is sent either, so only an upstream that caches an identical prefix implicitly gives the reduced rate (the shared system message is sent first and unchanged — not verified against a live endpoint) |
| NFR-3 | partial | SC-006 | **AC-1 not met** — a scorecard records the run id, corpus id and tool version but not the scored artefact's hash; the judge's model and prompt versions have nothing to record until the LLM judge is built. AC-2 holds for deterministic checks |
| NFR-4 | partial | SC-007 | AC-1 holds — the default branch's ruleset requires lint, the tests, both example-corpus evaluations, the report and the secret scan, with no bypass. AC-2 holds — scorecards are uploaded per corpus. **AC-3 not met** — the evaluation runs the deterministic path and does not invoke the target toolchain |
| NFR-5 | partial | SC-005 (AC-2: SC-009) | The architecture holds — a renderer is a self-contained package behind a registry. **AC-1 not met** — `Scorecard.kind` is a hardcoded `Literal["graph","ts","go"]`, so a new target also edits the evaluation model; the render pipeline hardcodes the TypeScript renderer's prompt directory and prompt id in the render cache key; and the `render` command carries TypeScript-specific flags and imports the TypeScript package by name to register it. **AC-2 not met** — no renderer-authoring documentation yet; a short contributor-guide section is planned first, the full guide with the second renderer |
| NFR-6 | partial | SC-002 | Holds when enrichment is disabled — canonical serialisation in the writer, and the same bytes feed the manifest hash and the golden assertion. AC-3 holds. **AC-1 and AC-2 not met on LLM-enabled runs** — the corpus-synthesis pass rewrites the graph without the canonical form, so the file on disk is neither canonical nor the bytes that were hashed (see FR-34). Goldens are captured without enrichment, so they never see this. **AC-4 not met** — the envelope is declared and CI asserts it, but drift fails CI-only tests rather than skipping the comparison with a reason |
| NFR-7 | partial | SC-002 | AC-2 and AC-3 hold — graph and manifest schema versions are independent of the application version; the manifest is `2.0.0`, strict-additive within `2.x` (nothing enforces it yet). **AC-1 not met** — the graph and the enrichment file carry their schema version only in the manifest (the enrichment file, a bare list, cannot hold one); the scorecards and the compile-check record carry it only in the file |
| NFR-8 | shipped | SC-004 | AC-1 holds — network use is limited to the configured provider's client and `git clone` of a URL the user gave; no code sends anything to the maintainers |

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
