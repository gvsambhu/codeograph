---
status: accepted
date: 2026-04-21
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-002 — Input-Agnostic Source Acquisition & Categorisation

## Context and Problem Statement

Stage 1 of the pipeline turns "some Java/Spring Boot project out there" into "a known set of source files the pipeline can reason about". Three concerns sit inside this stage and they are intertwined enough to decide together:

1. **Source acquisition** — where the codebase comes from (local path, git repo, zip).
2. **Build-system handling** — what, if anything, Codeograph does with `pom.xml` / `build.gradle(.kts)`.
3. **File categorisation & multi-module** — which files are in scope, which are skipped, and how sources belonging to different modules are labelled.

The tool must be input-agnostic: any reasonable Spring Boot project shape should work without special configuration. The design also has to leave room for v1.1 concerns (cross-module ref resolution, richer dep metadata) without painting Stage 1 into a corner.

## Decision Drivers

* **Realistic enterprise targets.** Multi-module Maven/Gradle projects are the common case in the audience this tool targets; single-module-only would be a credibility gap.
* **Pure-Python runtime.** Codeograph must not require the *target project's* build tooling (`gradle`, `mvn`, `gradlew`) to function. *(Note: ADR-003 later narrowed this constraint — a bundled JVM-based parsing helper is permitted; the prohibition is on shelling out to the project's own build system.)*
* **Least surprise.** File-skip behaviour should match what developers already expect — i.e. honour `.gitignore` rather than invent a new skiplist vocabulary.
* **Scope discipline.** Stage 1 must enumerate sources correctly and label them by module. It must *not* try to resolve cross-module references — that is parsing work and belongs to ADR-003.
* **Tractable Stage 0 implementation.** The v1 input layer should be buildable in a few days, not weeks.

## Considered Options

**Source acquisition**
* A1 — local path only
* A2 — local path + git URL
* A3 — local path + git URL + zip file  *(chosen)*

**Build-system handling**
* B1 — filesystem-only; ignore `pom.xml` / `build.gradle` entirely
* B2 — detect + fully parse build files (extract dep tree, versions, module list)
* B3 — detect + declare: record which build tool is present in the graph; don't parse contents  *(chosen)*

**File categorisation**
* C1 — hardcoded skiplist only (`target/`, `build/`, `.git/`, `.idea/`, `.gradle/`, `generated-sources/`, `node_modules/`)
* C2 — honour `.gitignore` via `pathspec`, with C1 as fallback when no `.gitignore` exists  *(chosen)*

**Multi-module**
* M1 — single-module v1; multi-module deferred to v1.1
* M2 — multi-module enumeration + module labelling in v1; cross-module reference resolution deferred to ADR-003  *(chosen)*

## Decision Outcome

* **Acquisition: A3 — support local path, git URL, and zip file.** The CLI autodetects the form of the `source` argument and acquires sources accordingly. Git and zip paths extract into a configurable temp dir (`settings.temp_dir`).
* **Build-system handling: B3 — detect + declare.** Stage 1 looks for `pom.xml`, `build.gradle`, `build.gradle.kts`, or `settings.gradle(.kts)`; records `build_system: maven | gradle | unknown` as metadata; does not parse contents. Richer build-file parsing is out of scope for v1 (see Deferred).
* **Categorisation: C2 — honour `.gitignore` via `pathspec`, hardcoded skiplist as fallback.** When the project root has a `.gitignore`, `pathspec` applies it. When absent, fall back to the hardcoded skiplist. Hidden directories (`.git/`, `.idea/`, `.gradle/`) are always skipped regardless.
* **Multi-module: M2 — enumerate all modules, label each source with its module.** Every `src/main/java` found recursively is in scope; each source file carries a `module` field derived from its nearest ancestor `pom.xml` / `build.gradle(.kts)`. Cross-module reference resolution is explicitly deferred to ADR-003.

## Consequences

* Good, because v1 accepts any of the three common ways an engineer hands over a codebase (local checkout, repo URL, archive from a ticket).
* Good, because enterprise multi-module Spring Boot projects — the realistic target — are handled end-to-end at the input layer.
* Good, because the tool remains pure-Python — no JVM or Gradle required on the user's machine.
* Good, because `.gitignore` respect means the tool "does what developers expect" for custom output dirs and generated sources without per-project configuration.
* Bad, because B3 means the graph carries `build_system: maven|gradle` but no dep list or versions in v1. Any analysis that wants dep information (e.g. "is this project on Spring Boot 2 or 3?") has to wait for a later ADR.
* Bad, because zip handling introduces path-traversal and extraction-bomb surface area (mitigated via `zipfile`'s member-path validation and a max-extracted-size cap in settings).
* Bad, because git URL handling requires `git` on the user's PATH; we document this in README rather than bundle a git client.
* Bad, because `pathspec` adds one small dependency. Trade accepted against the alternative of surprising skip behaviour.

## Confirmation

* Unit tests cover each acquisition mode with fixture inputs: a local multi-module repo, a `file://` git URL, and a pre-built zip archive.
* A golden-input test asserts that enumeration on a known multi-module Maven fixture produces the expected `(module, relative_path)` set.
* A `.gitignore` fixture test verifies a custom output dir listed in `.gitignore` is skipped.
* CI runs all three on every PR.

## Pros and Cons of the Considered Options

### A1 / A2 / A3 (acquisition)

* A1 is 10 lines and handles ~70% of use cases, but rejects the two natural "handover" flows (repo URL, archive attachment).
* A2 adds git support; requires `git` on PATH, gains the most common remote flow.
* A3 *(chosen)* adds zip; marginal code, but introduces extraction safety concerns that need explicit handling.

### B1 filesystem-only

* Good, because simplest possible implementation.
* Bad, because the graph has no notion of whether the project is Maven, Gradle, or ad-hoc — downstream renderers and eval can't reason about build-tool idioms.

### B2 detect + parse

* Good, because the graph gets full dep metadata (groupId/artifactId/version), enabling richer analysis (Spring Boot version, known vulnerable deps, etc.).
* Bad, because Maven parsing is cheap (`xml.etree`, ~20 lines) but **Gradle parsing is a sub-project**. `build.gradle(.kts)` is executable Groovy/Kotlin; reliable extraction requires running the Gradle daemon (needs JVM), parsing Groovy AST (no mature Python parser), or regex heuristics that silently miss variables / plugin DSLs / conditionals.
* Bad, because any of those three paths either violates the pure-Python-runtime constraint (JVM required) or accepts silent inaccuracy.

### B3 detect + declare *(chosen)*

* Good, because one `os.path.exists` check buys the graph a `build_system` metadata field.
* Good, because keeps v1 tractable and defers the Gradle-parsing rabbit hole without closing the door on it.
* Neutral, because downstream ADRs can upgrade to B2 later (for Maven first, Gradle later) without breaking the input layer contract.
* Bad, because dep metadata and multi-module tree from `settings.gradle` / `<modules>` are not available to the pipeline in v1 — we have to rediscover module boundaries by walking the filesystem.

### C1 hardcoded skiplist

* Good, because zero dependency, predictable.
* Bad, because surprises users whose projects generate code to non-standard dirs. Those dirs end up in the graph as "source" and pollute results.

### C2 `.gitignore` via `pathspec` *(chosen)*

* Good, because "matches what git does" is the least-surprising behaviour.
* Good, because custom output / generated-code dirs listed in `.gitignore` are skipped automatically.
* Neutral, because `pathspec` is a tiny pure-Python dep with no transitive baggage.
* Bad, because projects without a `.gitignore` still need the C1 fallback — so we carry both code paths.

### M1 single-module only

* Good, because simpler Stage 1 code and test surface.
* Bad, because most enterprise Spring Boot projects are multi-module; single-module-only makes the tool look like a toy.

### M2 multi-module enumeration + label *(chosen)*

* Good, because realistic enterprise codebases work end-to-end at the input layer.
* Good, because the scope is contained — we enumerate and label, we do not solve cross-module ref resolution.
* Bad, because downstream stages must handle name collisions (two `UserService.java` in different modules) — the `module` label on every source makes this tractable but not free.
* Bad, because settling on "nearest ancestor `pom.xml` / `build.gradle` defines the module" is a heuristic; projects with unconventional layouts may label sources in ways that surprise.

## More Information

**Pipeline contract coming out of Stage 1.** The Stage 1 output handed to Stage 2 (parsing, ADR-003) is:

```python
@dataclass(frozen=True)
class SourceFile:
    module: str              # e.g. "api", "service", "persistence"; "" for single-module
    rel_path: str            # POSIX-style, relative to project root
    abs_path: Path           # resolved absolute path

@dataclass(frozen=True)
class ProjectInput:
    root: Path
    build_system: Literal["maven", "gradle", "unknown"]
    modules: list[str]       # discovered module names; [""] for single-module
    sources: list[SourceFile]  # filtered by .gitignore + skiplist, scoped to src/main/java
```

Tests (`src/test/java`) and non-Java resources (`src/main/resources`) are intentionally **not** part of `sources` in v1. Tests may be added in v1.1 once parsing and graph schema (ADR-003, ADR-006) have stabilised on production code.

**Acquisition detection.** The CLI classifies the `source` arg by shape:
* starts with `http(s)://`, `git@`, ends with `.git` → git clone
* ends with `.zip` and exists as a file → zip extract
* otherwise → treat as local path; error if it doesn't exist or isn't a directory

Cloned/extracted sources land under `settings.temp_dir`; cleanup policy is on `settings.keep_temp` (default false).

**Safety.**
* Zip extraction validates each member path against the extraction root (no `../` escape). A `max_extracted_bytes` cap in settings aborts on extraction bombs.
* Git clone uses `--depth 1` by default (overridable). SSH URLs work only if the user has keys configured — documented, not solved.

**Deferred (not in v1, called out so downstream ADRs can land them):**
* **Cross-module reference resolution** — `api.UserController → service.UserService`. Lives in ADR-003 (parsing strategy) and ADR-006 (graph schema).
* **Build-file parsing for dep metadata** — Maven-only first pass (cheap), Gradle later. Warrants its own ADR when prioritised.
* **Test sources and resources in the graph** — v1.1 once production-code graph quality is proven.
* **Non-JVM inputs** — Kotlin-only projects, Spring Boot on Kotlin, etc. Explicitly out of scope for v1; reconsider after v1.1.

References:
* `pathspec` — https://pypi.org/project/pathspec/
* Python `zipfile` member-path safety (Python 3.12+ `Path.resolve()` idioms)
* Git shallow clone — https://git-scm.com/docs/git-clone#Documentation/git-clone.txt---depthltdepthgt

## Amendments

**2026-06-14 — Design-review pass (10 decisions).** A design review surfaced ten unmade or under-specified forks and edge cases; this single entry records the decisions for all ten. No prior locked fork is reversed — these fill gaps and clarify; several ratify the as-built behaviour.

1. **Module-name derivation.** The M2 `module` label is the **directory name of the nearest ancestor build file** (`pom.xml` / `build.gradle(.kts)`). Clarifies the "nearest ancestor … defines the module" heuristic in the Decision Outcome, which never specified *what* the name was (vs Maven `artifactId` or path-from-root).

2. **Stage-1 contract shape — ratifies as-built.** The Stage-1 → Stage-2 contract is the **nested** `CorpusSpec{corpus_root, acquisition_source, modules: list[ModuleSpec]}`, where each `ModuleSpec` owns its own `java_files` — *not* the flat `ProjectInput`/`SourceFile` sketch in **More Information** above. The interface-granularity axis (flat-with-labels vs modules-own-files) was never forked; the nested shape is now the recorded design. **Supersedes** the `SourceFile`/`ProjectInput` dataclass sketch in **More Information** and the Confirmation's "(module, relative_path) set" wording.

3. **Hybrid build system.** When **both** `pom.xml` and `build.gradle(.kts)` are present, **Maven wins**: emit `build_system = "maven"` and log the Gradle file as a secondary/ignored artefact. Rationale: only Maven gets `~/.m2` symbol resolution (ADR-003 CP2), so Maven is the meaningful classpath anchor.

4. **FR-24 malformed-input enumeration.** FR-24's 6 v1 negative-input classes are enumerated authoritatively (zip bomb, zip-slip, corrupt archive, git acquisition failure, empty corpus, no build file); this ADR's Confirmation gains a matching negative-test obligation and honours that enumeration.

5. **Source-arg classification — ratifies as-built.** The authoritative rule is **prefix-based**: `http(s)://`, `git@`, `git://` → git; `*.zip` (existing file) → zip; otherwise → local. **Supersedes** the "ends with `.git` → git clone" prose in **More Information** (Acquisition detection), which the implementation never followed. Consequence (accepted): a bare local path literally ending `.git` is treated as local, not a clone target.

6. **`build_system` value space.** **`unknown` is dropped.** A corpus with no recognised build file is **rejected upstream** with a clear error (it is not accepted and labelled "unknown"). `build_system` is now **`maven | gradle` only**. **Supersedes** the `build_system: maven | gradle | unknown` declaration in the Decision Outcome and aligns the design with the shipped `BuildTool` enum.

7. **Empty corpus.** A corpus with **no `.java` files in scope** after discovery → **fail loud**: user-readable message + non-zero exit. No empty-graph pass-through. (Pairs with #6 — both no-build-file and no-sources fail loud rather than degrade.)

8. **Zip internal layout.** If the archive contains **exactly one top-level directory** that holds the project (`projectname/src/…`), that directory is **stripped** and becomes the extraction root. Otherwise the archive root is treated as the project root. Extends the **Safety** section.

9. **`max_extracted_bytes` cap.** Default **500 MB**, citing GitHub's repository-size advisory limit as the anchor; **configurable** via settings. Replaces the unspecified "a `max_extracted_bytes` cap in settings" reference (Consequences + Safety) with a cited, named default.

10. **Malformed `.gitignore`.** A `.gitignore` that `pathspec` cannot parse → **log a warning and fall back to the C1 hardcoded skiplist** (do not fail the run, do not silently produce wrong scoping). Extends the C2 decision.

**New Confirmation items (from this amendment):**
* Negative tests for the 6 FR-24 classes assert graceful failure with specific messages (#4).
* A no-build-file corpus and a no-`.java`-files corpus each exit non-zero with a user-readable error (#6, #7).
* A zip wrapping a single top-level project dir extracts with that dir stripped (#8).
* A malformed `.gitignore` logs a warning and the run proceeds on the C1 skiplist (#10).
