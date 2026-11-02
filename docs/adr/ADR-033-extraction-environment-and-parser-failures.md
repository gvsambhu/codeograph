---
status: proposed
date: 2026-11-01
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-033 — Extraction Environment and Parser Failures

## Context and Problem Statement

**State at the time of this decision:** codeograph 0.5.0, `main` at `420f2b5` (2026-11-01). ADR text is
cited as it stands at that commit. No symbol solver is configured in the shipped parser, so no
third-party reference resolves on any machine; the decisions below govern resolution as designed.

The requirements make the knowledge graph *"a function of the corpus and the tool alone"* — nothing
outside them may change a byte of it (FR-34) — and require byte-identical graphs within a declared,
pinned execution envelope (FR-10 AC-2, NFR-6). Two decisions in ADR-003 let something outside the corpus
and the tool change the graph.

**1 · Third-party resolution reads the machine's local Maven repository.** ADR-003's classpath fork chose
CP2: JavaParser's symbol solver adds a JAR solver for each dependency *"resolved from a parsed `pom.xml` +
`~/.m2/repository/` lookup"*. That makes the graph depend on what the local repository holds:

* **Its contents vary by machine.** A repository holds whatever earlier builds downloaded. Version ranges
  resolve to whatever was newest when Maven ran; a SNAPSHOT coordinate points at different builds over
  time; a repository may hold several versions of one artefact, or none. The same corpus on two machines
  can yield different resolved edges — and, downstream, different CBO values (ADR-004 counts resolved call
  targets) and a different selection (ADR-009 ranks on CBO).
* **It can resolve against versions the build does not use.** Maven's own resolution — parent POMs,
  imported BOMs, `dependencyManagement`, properties, profiles, ranges, nearest-wins mediation, exclusions —
  is the only authority on which versions a project builds with, and Maven keeps no lockfile. A parser that
  reads `pom.xml` and looks files up approximates that resolution; where the approximation differs, edges
  resolve against the wrong API.
* **The location is hardcoded.** Maven's local repository is configurable (`settings.xml`
  `<localRepository>`, `-Dmaven.repo.local`); a fixed `~/.m2/repository` misses those setups.
* **Gradle projects get no third-party resolution at all** under CP2.

The execution envelope ADR-007 declares pins the operating system and the JDK; it does not include a
local repository.

**2 · A parser-process failure changes the graph.** ADR-003's 2026-06-14 amendment sends the affected
files to the regex extractor when the parser *subprocess* fails — a JVM crash, an out-of-memory error, a
protocol desync, a hang — and FR-31 AC-2 requires exactly that: degrade the affected files and continue.
But a crash or a hang is a property of the machine and the moment, not of the file; two runs of one corpus
can produce different graphs. Nothing distinguishes a *file* the parser cannot parse (deterministic) from a
*parser* that failed (transient).

**3 · Reduced extraction fidelity has no record to land in.** ADR-003 says a file that fell back to the
regex extractor, and a name-only stub, are *"recorded in the run manifest"*; the manifest has no such field
and its schema forbids extra fields (ADR-025). The requirements need the record: every degraded file
recorded with its reason and reported at the end of the run (FR-31 AC-3, AC-4), conditions that reduce
resolution reported with their remediation (FR-40 AC-3, AC-4), and excluded non-Java sources visible in the
run's output (FR-30 AC-4).

**This ADR decides where third-party resolution comes from, how the resolution environment is recorded,
what a parser-process failure does, and where the run records everything that reduced extraction
fidelity.** It supersedes ADR-003's classpath fork and extends ADR-003's
failure model. ADR-003's parser choice and extraction approach are unchanged. ADR-021 (determinism
contract, v1.1) remains the home of the full contract; this ADR decides two specific sources of variation
ahead of it.

## Decision Drivers

* **Determinism / determinism boundary clarity** — by default, the graph is the same for the same corpus
  and tool on every machine (FR-34, NFR-6).
* **Resolve against what the build uses, or not at all** — a resolved edge that points at the wrong
  version's API is worse than an unresolved one, which FR-40 already makes visible.
* **No silent failures** — reduced resolution and transient degradation are reported, never inferred
  (FR-40 AC-3, AC-4; FR-31 AC-3).
* **The target's build tooling is never invoked** (requirements assumption 4).
* **Least surprise** — no hardcoded locations; configuration follows the documented precedence (FR-38).

## Considered Options

### Fork 1 — Where third-party resolution comes from

* (a) The local repository as found (CP2), with its contents fingerprinted into the manifest so a
  difference is detected.
* **(b) None by default; opt in by supplying the classpath the project's own build resolved. ✅**
* (c) Full build-file resolution inside the tool, for Maven and Gradle (ADR-003's CP3).
* (d) Invoke the project's build tool to resolve the classpath.

### Fork 2 — The shape of the classpath input

* (a) One merged classpath for the whole corpus.
* **(b) One classpath per module, with a single-file shortcut. ✅**

### Fork 3 — How the resolution environment is recorded

* (a) Not recorded.
* (b) A single summary hash in the manifest.
* **(c) A per-JAR record in its own artefact, plus a summary hash in the manifest. ✅**

### Fork 4 — What a parser-process failure does

* (a) Degrade the affected files to the regex extractor, as ADR-003 decides.
* **(b) Restart the parser and retry each affected file once, singly; degrade only a file whose retry
  fails, and flag the run. ✅**
* (c) Fail the run.

### Fork 5 — Where reduced extraction fidelity is recorded

* (a) Split across the ADRs that cause it, each pointing at a manifest section.
* **(b) One extraction report, written by `run`, owned by this ADR. ✅**
* (c) A section of the manifest.

## Decision Outcome

### Fork 1 — Corpus-only by default; build-resolved classpath as the opt-in: (b)

* **Default:** the symbol solver is assembled from the corpus's source roots and the JDK only — no JAR
  solvers. A reference into a third-party library is emitted unresolved, with its identifier (ADR-003's
  edge fork; FR-40 AC-1). The tool never reads a local repository and never parses `pom.xml` or a Gradle
  build file for resolution.
* **Opt-in:** a **classpath setting** names the classpath the project's own build resolved. It resolves
  through the documented precedence — invocation flag, environment, local environment file, project
  config file — and has no built-in default (FR-38 AC-1). Its name follows ADR-001's naming rule and is
  fixed at implementation.
* **Producing the input** is the user's step, with their own build tool — for example
  `mvn dependency:build-classpath -Dmdep.outputFile=classpath.txt`, or a Gradle task that prints a
  configuration's resolved files. The tool reads the result; it never runs the build (assumption 4). Gradle
  projects gain third-party resolution this way, which CP2 never offered.
* **Validated at startup:** every listed entry must exist and be readable. A setting naming a missing or
  unreadable file fails before any work, with exit status 1 and a message naming the entry (FR-38 AC-2;
  ADR-031).
* **Entries that are the corpus's own output are dropped.** A build-produced classpath can list the
  corpus's own modules — a reactor build lists their `target/classes` directories, a standalone one their
  installed JARs. Those types already come from the corpus's source, and their bytes change with every
  build. An entry whose path lies inside the corpus root, or a JAR whose embedded coordinates match a
  corpus module's, is dropped and named in the end-of-run report. Any other directory entry is accepted.
* **Reported at the end of every run** (FR-40 AC-3, AC-4): with no classpath, *third-party resolution is
  off*, with the setting that enables it; with one, the number of entries used, the entries dropped, and
  the unresolved-call count.
* **Read by `run`, and by evaluation's reproducibility re-run** — and there only to supply the entries
  again: the re-run's resolution mode always comes from the run's record, so a classpath setting present
  at evaluation is ignored when the run was corpus-only (ADR-032 Fork 4).
* **The classpath is part of the declared envelope when used.** A corpus-only graph is a function of the
  corpus and the tool alone (FR-34). A classpath-mode graph is reproducible given the same classpath
  record as well — the record is the envelope's resolution component (NFR-6 AC-4), and ADR-032's check
  compares it before comparing graphs. The golden harness and CI always run corpus-only, whatever a
  contributor's environment sets (see *Constraint flagged for ADR-007*).

### Fork 2 — Per-module classpaths: (b)

* Modules resolve their own dependencies, and two modules can resolve different versions of one library.
  The setting therefore takes **either** one file, applied to every module, **or** a mapping from module
  (identified by its corpus-relative path, as FR-30 AC-1 labels it) to file.
* **The mapping lives only in the project config file**, as a table from module path to file. The
  invocation flag, the environment and the local environment file carry the single-file form only. The
  layers resolve as FR-38 AC-1 orders them, each layer's value whole: a single file given at a higher
  layer replaces a lower layer's mapping.
* A module the mapping omits resolves corpus-only, and the end-of-run report names it.
* A classpath file is a list of JAR paths, separated by the platform path separator (as Maven writes it) or
  one per line.

### Fork 3 — A per-JAR record plus a summary hash: (c)

* **`analysis/classpath.json`**, written by `run` when a classpath is used. Per module, per entry, sorted:
  - the SHA-256 of the JAR's bytes — **the authoritative identity**, which distinguishes two locally
    installed builds of one SNAPSHOT that share a file name; for a directory entry, the SHA-256 of the
    corpus-fingerprint-style listing of its files (ADR-032 Fork 4's serialisation);
  - group id, artefact id and version, read from the JAR's embedded Maven metadata when it holds exactly
    one set; for a SNAPSHOT, the timestamped build where that metadata records one (it often does not —
    the SHA-256 identifies the build regardless);
  - otherwise — no metadata, or several sets, as in a shaded JAR — the file-name stem alone.

  Per module, the record also names the entries dropped as the corpus's own output (Fork 1).

  **No paths and no repository location are recorded** — they are machine-specific, may contain a user
  name, and add nothing once content is hashed. The same JARs at different paths therefore record
  identically.
* **The manifest** carries the resolution mode — corpus-only or classpath — the record's pointer and
  SHA-256, and a summary hash over the record. Corpus-only is stated explicitly, never implied by absence
  (FR-33 AC-4).
* Two graphs are then comparable with certainty about what each was resolved against: equal summary
  hashes mean the same JARs; different ones, and the records show which artefact or version differs.

### Fork 4 — Retry once, then degrade and flag: (b)

* **Two failure kinds are distinguished.** A *file-level* failure — the parser runs and rejects the file —
  degrades that file to the regex extractor, as ADR-003 decides; it is deterministic. A *process-level*
  failure — the parser subprocess crashes, runs out of memory, desynchronises, or does not answer within
  the timeout — is treated as transient.
* **One retry per file, never more.** On a process-level failure the parser subprocess is restarted and
  the files that were in flight are retried **one at a time**, so a failure in the retry identifies its
  file. A file whose own retry also fails degrades to the regex extractor; the subprocess is restarted
  again for the remaining retries, and then resumes normal batches for the files not yet parsed. A file
  that was merely in flight beside a failing one parses normally. Every file is retried at most once, so
  the run ends in bounded time — at worst one restart per file.
* **A transient degradation is flagged:** each file degraded after its retry is recorded in the
  extraction report (Fork 5) with its reason and a transient marker, the manifest carries a run-level
  transient-degradation flag, and the end-of-run report names the files (FR-31 AC-3, AC-4). A restart
  whose retries all succeed changes nothing and is not recorded.
* **The timeout** is a setting with a stated default, chosen at implementation from a measurement on the
  committed example corpora and documented with that basis; no published value applies.
* **A file that crashes the parser every time is flagged too.** The tool cannot tell a deterministic crash
  from a repeated transient one, so such a file is degraded and marked transient on every run, and its
  corpus's reproducibility check skips (ADR-032 Fork 4) until the file or the parser changes. A JDK that
  is absent from the start is not transient: every file takes the regex extractor, the report states the
  condition, and no transient flag is set — the JDK's presence is part of the recorded envelope.

### Fork 5 — One extraction report: (b)

**`analysis/extraction-report.json`**, written by `run` at the end of Pass 0, with its own schema version
(NFR-7 AC-1), indexed from the manifest with its SHA-256. It holds, sorted:

* **degraded files** — corpus-relative path, the extraction that produced the node (full parse, regex
  extractor, or name-only stub — the values the graph schema enumerates), the reason (the parser's error,
  with any machine-specific path removed), and the transient marker (Fork 4) where it applies;
* **excluded sources** — every file discovery recognises as source in a language other than Java (Kotlin,
  Groovy, Scala and the like, by extension), with its path and language (FR-30 AC-4). Resources,
  documentation and other non-source files are not listed;
* **conditions** — every run-level condition that reduced fidelity, each with its remediation or a
  statement that none is known (FR-40 AC-3, AC-4): third-party resolution off, and the setting that enables
  it; modules with no classpath; classpath entries dropped as the corpus's own output; no JDK available.

The **manifest** carries per-category counts and the report's pointer — never the per-file lists, which
grow with the corpus. The **end-of-run report** (FR-31 AC-3, FR-40 AC-3) is built from the extraction
report, so the console and the file cannot disagree.

The graph keeps recording, on each node, which extraction produced it (FR-31 AC-1); the report adds the
reason and the run-level view. Every entry except the transient marker is a function of the corpus, the
tool and the declared environment.

### Constraints flagged for other ADRs

#### Constraint flagged for ADR-025
The manifest records the extraction report's pointer and SHA-256 and its per-category counts (Fork 5), the
resolution mode, the classpath record's pointer, SHA-256 and summary hash (Fork 3), and the run-level
transient-degradation flag (Fork 4) — additive.

#### Constraint flagged for ADR-029
`analysis/classpath.json` and `analysis/extraction-report.json` join the run-directory layout, both
produced by `run`.

#### Constraint flagged for ADR-032
Its `reproducibility` check reads the resolution record, the classpath summary hash and the transient
flag, and re-runs in the recorded mode (Fork 1).

#### Constraint flagged for ADR-003
On acceptance, the classpath fork — with the 2026-06-14 amendment's item 3 (the empty-`~/.m2` hint) and the
deferred Gradle dependency resolution, both discharged here — carries a *superseded by ADR-033* note; the
failure policy's and the 2026-06-14 amendment's *"recorded in the run manifest"* point at the extraction
report (Fork 5), and the subprocess failure model (item 1) at Fork 4.

#### Constraint flagged for ADR-004
In corpus-only mode, calls into libraries are unresolved, so they leave CBO's count of resolved call
targets; CBO, and the selection ranked on it (ADR-009), follow the recorded resolution mode. Whether the
cited CBO bands assume library coupling is for ADR-004 to state.

#### Constraint flagged for ADR-007
The golden harness and CI run corpus-only, whatever classpath setting the environment carries, and the
envelope ADR-007 declares records the resolution mode beside the operating system and JDK.

#### Constraint flagged for ADR-021
When the determinism contract is written, it absorbs or cites this ADR's two rules — the resolution
environment as a recorded part of the envelope, and transient degradation as a flagged exception.

## Consequences

* Good, because by default the graph is identical for the same corpus and tool on every machine.
* Good, because opted-in resolution uses exactly the versions the project builds with, never an
  approximation of Maven's resolver.
* Good, because Gradle projects can resolve third-party references, which CP2 never allowed.
* Good, because a one-off parser crash no longer changes the graph, and the rare repeated failure is
  visible in the manifest and the report.
* Bad, because by default every call into Spring, JPA or another library stays unresolved — ADR-003's
  stated reason for rejecting CP1. The calls are still emitted with their identifiers, and the end-of-run
  report names the setting that resolves them. User-visible; it reaches the README in the shipping PR.
* Bad, because library-aware edges need one extra step from the user: producing a classpath with their
  build tool.
* Bad, because the parser bridge gains restart-and-retry logic and a timeout setting.
* Bad, because a file that crashes the parser every time is flagged transient on every run, so its
  corpus's reproducibility check skips until the file or the parser changes.
* Bad, because in the default mode CBO counts no library call targets, so CBO values and the selection
  ranked on them differ from a classpath-mode run of the same corpus. Both are recorded with their mode.
* Bad, because a multi-module project that wants per-module classpaths must write the mapping in its
  config file; the command line and the environment carry one file only.
* Good, because degraded files, excluded sources and reduced-resolution conditions finally have one
  record, and the end-of-run report is generated from it.
* Neutral, because the manifest gains a resolution section and counts, and the run directory an extraction
  report on every run and a classpath record when one is used.

## Confirmation

1. A run with no classpath setting builds no JAR solver; a call into a third-party library is emitted
   unresolved with its identifier, and the end-of-run report says third-party resolution is off and names
   the setting (integration test).
2. Two runs of one corpus — one from a machine with a populated local Maven repository, one with an empty
   repository, neither with a classpath setting — produce byte-identical graphs (integration test with two
   repository fixtures).
3. A classpath setting naming a missing JAR fails at startup with exit status 1 and a message naming the
   entry, before any work (unit test).
4. With a per-module mapping, a call resolved through module A's classpath is resolved, and the same call
   in a module the mapping omits is emitted unresolved, with that module named in the report (integration
   test on a two-module fixture).
5. `analysis/classpath.json` lists each JAR's coordinates and SHA-256 and contains no path; the same JARs
   copied to a different directory produce an identical record and summary hash (unit test).
6. A run with no classpath records the corpus-only mode in the manifest explicitly (unit test).
7. Killing the parser subprocess once mid-run produces the same graph as an uninterrupted run, and no
   transient flag (integration test).
8. A file that crashes the parser in both the first and the restarted subprocess degrades to the regex
   extractor, is recorded in the extraction report with a transient marker, sets the manifest's transient
   flag, and is named in the end-of-run report; the files that were in flight beside it parse at full
   fidelity with no marker (integration test with a fault-injecting parser stub).
9. Running with no JDK available degrades every file to the regex extractor, states the condition in the
   report, and sets no transient flag (integration test).
10. A corpus containing one unparseable Java file and one Kotlin file produces an extraction report listing
    the Java file as degraded with its reason and the Kotlin file as excluded, the manifest's counts match,
    and the end-of-run report names both (integration test).
11. The extraction report contains no absolute path, and two runs of one corpus from different directories
    produce identical reports (unit test).
12. A classpath listing a corpus module's `target/classes` directory and another module's installed JAR
    drops both, names them in the end-of-run report and the record, and the summary hash is unchanged after
    rebuilding those modules (integration test on a two-module fixture).
13. A per-module mapping in the config file applies per module; the same setting given as a single file on
    the command line replaces the mapping for every module (unit test).
14. A JAR with two embedded Maven coordinate sets is recorded by its file-name stem and SHA-256 (unit test).

## Pros and Cons of the Considered Options

### Fork 1 — Where third-party resolution comes from

**(a) The local repository as found, fingerprinted.**
* Good, because every machine gets the best resolution its repository allows.
* Good, because the fingerprint explains a difference instead of reporting a false defect.
* Bad, because cross-machine reproducibility is detected, never guaranteed, and the approximation of
  Maven's resolver can still resolve against versions the build does not use.

**(b) None by default; build-resolved classpath as the opt-in. ✅ Chosen.**
* Good, because the default graph depends on the corpus and the tool alone.
* Good, because the opt-in uses exactly the build's own versions, works for Gradle, and records itself.
* Bad, because the default leaves library calls unresolved, and the opt-in needs a user step.

**(c) Full build-file resolution inside the tool.**
* Good, because resolution needs no user step.
* Good, because it would cover Gradle as well as Maven.
* Bad, because it re-implements two build tools' resolvers and still depends on what is downloaded locally.

**(d) Invoke the build tool.**
* Good, because it resolves exactly what the build resolves.
* Good, because it needs no user step.
* Bad, because it runs the target's build tooling, which assumption 4 rules out — slow, networked, and
  possibly executing build plugins.

### Fork 2 — The shape of the classpath input

**(a) One merged classpath.**
* Good, because it is one file to produce.
* Good, because single-module projects need nothing more.
* Bad, because where modules resolve different versions of one library, a merged list must pick one.

**(b) Per module, with a single-file shortcut. ✅ Chosen.**
* Good, because each module resolves against its own versions.
* Good, because single-module projects still supply one file.
* Bad, because a multi-module project supplies, and keeps current, one file per module.

### Fork 3 — How the resolution environment is recorded

**(a) Not recorded.**
* Good, because it costs nothing.
* Good, because the manifest stays smaller.
* Bad, because two graphs resolved against different JARs cannot be told apart.

**(b) A summary hash only.**
* Good, because one comparison answers "same JARs?".
* Good, because the manifest grows by one value.
* Bad, because when hashes differ, nothing says which artefact or version differs.

**(c) A per-JAR record plus a summary hash. ✅ Chosen.**
* Good, because one comparison answers "same JARs?", and the record answers "which differ?".
* Good, because it follows the layout's rule that what grows with the corpus gets its own file.
* Bad, because a run with a classpath writes one more artefact.

### Fork 4 — What a parser-process failure does

**(a) Degrade, as ADR-003 decides.**
* Good, because no work is lost.
* Good, because it needs no new logic.
* Bad, because a one-off crash changes the graph, and nothing records that the cause was transient.

**(b) Retry each affected file once, singly, then degrade and flag. ✅ Chosen.**
* Good, because the common case — a single crash — yields the normal graph, and a file that was merely in
  flight beside a failing one is never degraded.
* Good, because the rare case is flagged, so a reproducibility check can tell an environment problem from a
  defect, and FR-31's degrade-and-continue holds.
* Bad, because the bridge gains restart logic and a timeout to state, and a corpus with many crashing files
  pays one restart per file.

**(c) Fail the run.**
* Good, because every graph that is produced is deterministic.
* Good, because it is simple.
* Bad, because a one-off crash discards the whole run, and it contradicts FR-31 AC-2.

### Fork 5 — Where reduced extraction fidelity is recorded

**(a) Split across the causing ADRs, pointing at a manifest section.**
* Good, because each rule sits beside the decision that causes it.
* Good, because no new artefact.
* Bad, because no single place defines the record, and the per-file lists grow inside the file every
  consumer reads.

**(b) One extraction report. ✅ Chosen.**
* Good, because one artefact, with one owner, answers FR-30 AC-4, FR-31 AC-3/AC-4 and FR-40 AC-3/AC-4.
* Good, because the end-of-run report and the file are generated from one source, and the manifest stays an
  index.
* Bad, because every run writes one more artefact.

**(c) A manifest section.**
* Good, because consumers already read the manifest.
* Good, because no new file.
* Bad, because it grows with the corpus inside the index every consumer reads, and extends a schema that
  forbids extra fields.

## More Information

### Relationships

* **ADR-003** (parsing strategy) — this ADR supersedes its classpath fork and extends its failure model;
  the parser choice and extraction approach are unchanged.
* **ADR-004** (complexity model) — CBO counts resolved call targets, so its value follows the resolution
  mode recorded here (a constraint flagged above).
* **ADR-007** (golden-graph pattern) — its declared envelope gains the resolution mode, never a local
  repository; goldens are captured corpus-only and are stable on every machine.
* **ADR-009** (rendering budget cap) — selection ranks on CBO, so it too follows the resolution mode.
* **ADR-021** (determinism contract, v1.1) — absorbs or cites this ADR's two rules.
* **ADR-025** (manifest schema) — the resolution section and the transient flag.
* **ADR-029** (output layout and ownership) — `analysis/classpath.json` and
  `analysis/extraction-report.json` in the run directory.
* **ADR-031** (command outcomes and consent) — an invalid classpath setting exits with 1.
* **ADR-032** (evaluation check semantics) — `reproducibility` reads the classpath record and the flag.

### Requirements touched

FR-10 AC-2 · FR-30 AC-4 · FR-31 AC-1, AC-2, AC-3, AC-4 · FR-33 AC-4 · FR-34 · FR-38 AC-1, AC-2 ·
FR-40 AC-1, AC-3, AC-4 ·
NFR-6 AC-3, AC-4 · assumptions 2 and 4.

### References

* Apache Maven, *dependency:build-classpath* —
  https://maven.apache.org/plugins/maven-dependency-plugin/build-classpath-mojo.html
* Apache Maven, *POM Reference — dependency version requirement specification* (version ranges) —
  https://maven.apache.org/pom.html#Dependency_Version_Requirement_Specification
* Apache Maven, *Configuring Maven* (the local repository location) —
  https://maven.apache.org/guides/mini/guide-configuring-maven.html
* JavaParser symbol solver — https://www.javadoc.io/doc/com.github.javaparser/javaparser-symbol-solver-core/

### Deferred

* The full determinism contract — per-field classification and consumer guarantees — ADR-021 (v1.1).
