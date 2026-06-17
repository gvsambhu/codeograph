---
status: accepted
date: 2026-06-17
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-026 — Release & Version Management

## Context and Problem Statement

Codeograph emits a version string in three places that a user or downstream consumer can observe: the `--version` CLI output, the package metadata on the index, and the `codeograph_version` field recorded in every run manifest (ADR-022 / ADR-025). Yet the project has no stated policy for *what that number means, when it changes, or where it is authored*. The number is currently hand-maintained in two locations, which can drift apart.

A versioning policy must answer four entangled questions:

1. **Which scheme** governs the number (and what each bump signifies).
2. **Whether the output contract** (the graph and manifest schemas) is part of the tool's public surface for compatibility purposes — or tracked separately.
3. **What the initial version is**, and **when the tool commits to a stable public API** (the `1.0.0` trigger).
4. **Where the number is authored** (the single source of truth) and how it is read at runtime.

A boundary must be drawn up front: the **tool/application version** (this ADR's concern) is distinct from the **graph schema version** (governed by ADR-006) and the **manifest schema version** (governed by ADR-025). Those artefact schemas already carry their own independently-governed semantic versions inside the output. This ADR governs only the application version.

## Decision Drivers

* **Industry-standard pattern / reviewer recognition** — versioning, runtime version access, and source-of-truth follow established Python-ecosystem norms (SemVer, PEP 440, `importlib.metadata`).
* **Honest compatibility signalling** — a version bump must truthfully indicate the nature of a change; a breaking change must never ship silently under a non-breaking bump.
* **Single source of truth** — the version is declared once; duplicated copies that can drift are eliminated.
* **Forward compatibility with v1.1** — additive evolution (e.g. a second render target) maps to a routine bump without a scheme change.
* **Separation of concerns** — the application version and the per-artefact schema versions are independent version lines, each tracking exactly one thing.

## Considered Options

### Fork 1 — Versioning scheme

* (a) CalVer (date-based, e.g. `YY.MM`).
* **(b) SemVer (`MAJOR.MINOR.PATCH`), human-decided at release. ✅**
* (c) SemVer auto-derived from conventional-commit messages.

### Fork 2 — Output-contract coupling

* (a) Coupled — a breaking graph/manifest schema change forces a tool MAJOR bump.
* **(b) Decoupled — the application version and the artefact schema versions evolve independently. ✅**

### Fork 3 — Initial version and the `1.0.0` trigger

* (a) Publish `1.0.0` immediately.
* **(b) Start at `0.x`; publish `1.0.0` at the stability gate. ✅**
* (c) Remain `0.x` indefinitely (no stability commitment).

### Fork 4 — Version source of truth

* **(a) Static field in `pyproject.toml`, read at runtime via `importlib.metadata`; no hand-maintained attribute. ✅**
* (b) A hand-maintained `__version__` attribute in package source is the source.
* (c) Derived from version-control tags (`setuptools-scm` / `hatch-vcs`).

## Decision Outcome

### Fork 1 — Versioning scheme: (b) SemVer, human-decided

The application version is **SemVer `MAJOR.MINOR.PATCH`**, expressed in a PEP 440-valid form. Bump semantics:

* **MAJOR** — a backward-incompatible change to the public surface (CLI flags or observable behaviour).
* **MINOR** — a backward-compatible feature increment (a design-driven development increment that adds capability without breaking existing behaviour).
* **PATCH** — a backward-compatible bug fix.

The bump is **applied when the increment's code ships** (the release event), not when an upstream design document changes. The bump size is **decided by a human at release time**, not auto-derived from commit messages: an auto-derived bump is only as reliable as the breaking-change markers in each commit, and a single mismarked commit would silently ship a breaking change under a non-MAJOR bump.

### Fork 2 — Output-contract coupling: (b) Decoupled

The application version and the per-artefact schema versions are **independent version lines**:

* A tool **MAJOR** bump is triggered **only** by a backward-incompatible change to the CLI surface or observable behaviour.
* A breaking change to the **graph schema** (ADR-006) or **manifest schema** (ADR-025) is signalled by that artefact's own `schema_version`, which is carried inside the output. It does **not** force a tool MAJOR bump.
* **Output-format compatibility is therefore determined by the artefact `schema_version`, not by the application version.** A consumer scripting against the graph or manifest output pins or checks `schema_version`; a consumer concerned with CLI invocation pins the application version.

This delegates output-compatibility signalling to the schemas that already self-describe their version, and keeps the application MAJOR meaningful as "the way the tool is invoked or behaves changed."

#### Constraint flagged for documentation

The public README and output documentation must state that output-format stability is governed by the artefact `schema_version`, independent of the application version. Without this statement a consumer could wrongly assume that pinning the application version guarantees output stability.

### Fork 3 — Initial version and the `1.0.0` trigger: (b) `0.x` then `1.0.0` at the gate

* The initial published version is **`0.5.0`**.
* The tool remains in **`0.x`** through development. Per SemVer's major-version-zero rule, the public API is not promised stable while in `0.x`; in-progress changes to the CLI and output schemas remain free of a compatibility-break cost.
* **`1.0.0` is published at the stability gate** — the point at which the CLI surface and the output schemas are frozen and the project commits to backward-compatible evolution thereafter.
* Post-`1.0.0`, an additive feature release (for example, a second render target) bumps **MINOR** (`1.1.0`); a backward-incompatible change bumps **MAJOR** (`2.0.0`); a fix bumps **PATCH**.

The technical rationale for deferring `1.0.0`: while the design is still being revised, promising stability would force a MAJOR bump on routine, expected churn. Remaining in `0.x` until the contract settles keeps those changes cost-free, then `1.0.0` is a single deliberate commitment rather than an arrival point of a counter. Pre-`1.0.0` version numbers carry no compatibility guarantee; their exact value is informational only.

### Fork 4 — Version source of truth: (a) Static in `pyproject.toml` + `importlib.metadata`

* The version is declared **once**, in the `pyproject.toml` project metadata.
* It is read at runtime via **`importlib.metadata.version("codeograph")`**; the CLI exposes it through `click`'s version option reading package metadata (no version string literal passed in code).
* **No hand-maintained `__version__` attribute** is kept in package source; this removes the duplicated, drift-prone copy.
* The `codeograph_version` recorded in the run manifest (ADR-022 / ADR-025) is sourced from the same package metadata, so all three observable version strings derive from one declaration.

The exact build-backend configuration (static field vs the backend's version hook) depends on the build backend declared in `pyproject.toml` and is settled at implementation time; the decision here is that the single authored location is the project metadata, surfaced via `importlib.metadata`.

## Consequences

* Good, because the application version is a single honest signal for CLI/behaviour compatibility, while output compatibility is tracked precisely by the self-describing artefact `schema_version` — no redundant coupling between the two.
* Good, because one authored source for the version eliminates the prior two-location drift.
* Good, because remaining in `0.x` keeps in-flight contract changes free of a compatibility-break cost, and `1.0.0` becomes a single deliberate stability commitment.
* Good, because a human-decided bump prevents a mismarked commit from silently shipping a breaking change under a non-MAJOR release.
* Good, because additive v1.1 capability maps to a routine MINOR bump with no scheme change.
* Bad, because a consumer who pins only the application version may still receive an output-schema change within the same application MAJOR; mitigated by the documented `schema_version` contract (see the flagged documentation constraint).
* Bad, because a human-decided bump means the version is not derived automatically; the release step requires a deliberate judgement (accepted — the automated alternative risks silent mis-bumps).
* Neutral, because version-control-tag derivation and commit-driven automation are not adopted in v1; both remain available as later migrations without changing the runtime read (see Deferred items).

## Confirmation

1. `importlib.metadata.version("codeograph")` returns the version declared in `pyproject.toml`; a test asserts the runtime value equals the declared metadata value.
2. `codeograph --version` prints a non-empty version string equal to the package metadata version (asserted by a CLI test).
3. A static check confirms no hand-maintained `__version__` string literal remains as an independent source in package code (the attribute, if present, resolves from `importlib.metadata`).
4. The initial published version declared in `pyproject.toml` is `0.5.0`.
5. The `codeograph_version` field recorded in a run manifest equals the package metadata version (asserted by an integration test on a sample run).
6. The output documentation states that output-format compatibility is governed by the artefact `schema_version`, independent of the application version (presence check).

## Pros and Cons of the Considered Options

### Fork 1 — Versioning scheme

**(a) CalVer.**
* Good, because the release date is immediately legible from the number.
* Good, because it suits tools where currency matters more than an API-stability promise.
* Bad, because it carries no backward-compatibility signal — a consumer cannot infer from the number whether an upgrade is safe.
* Bad, because the project's primary value is a stable output contract, which CalVer cannot express.

**(b) SemVer, human-decided. ✅ Chosen.**
* Good, because the number directly signals backward-compatibility expectations (MAJOR/MINOR/PATCH).
* Good, because the v1 → v1.1 milestone language maps cleanly onto MAJOR.MINOR.
* Good, because a human gate at release prevents silent breaking releases.
* Bad, because the bump requires a deliberate human judgement at each release rather than being automatic.

**(c) SemVer auto-derived from conventional commits.**
* Good, because the version and changelog are produced automatically in CI.
* Good, because it removes manual bump bookkeeping.
* Bad, because the bump is only as reliable as the breaking-change marker discipline in every commit; a single missed marker ships a break under a non-MAJOR bump.
* Neutral, because it can be adopted later once breaking-change marking is enforced.

### Fork 2 — Output-contract coupling

**(a) Coupled.**
* Good, because the application version becomes a single compatibility signal covering output as well.
* Good, because it is the simplest mental model for a consumer who reads only the application version.
* Bad, because it couples two version lines and drags the whole tool to a MAJOR bump for a pure output-schema change with an unchanged CLI.
* Bad, because it is partly redundant with the artefact `schema_version` that already self-describes output compatibility.

**(b) Decoupled. ✅ Chosen.**
* Good, because it is consistent with the project's existing per-artefact schema versioning, where each schema owns its own compatibility signal.
* Good, because the application MAJOR stays meaningful as "invocation or behaviour changed."
* Good, because it reduces application MAJOR churn.
* Bad, because a consumer who pins only the application version may receive an output change within a major; mitigated by a documented requirement to track `schema_version`.

### Fork 3 — Initial version and the `1.0.0` trigger

**(a) Publish `1.0.0` immediately.**
* Good, because it states a stability commitment from the first release.
* Bad, because the contract is still being revised; routine in-progress changes would force MAJOR bumps almost immediately.
* Bad, because it spends the first MAJOR on expected early churn rather than a genuine breaking change.

**(b) `0.x` then `1.0.0` at the gate. ✅ Chosen.**
* Good, because in-progress changes stay free of a compatibility-break cost while the contract settles.
* Good, because `1.0.0` becomes a single deliberate stability commitment at a defined gate.
* Good, because it matches the established pattern of tools that mature through `0.x` before committing a public API.
* Bad, because pre-`1.0.0` numbers carry no compatibility guarantee and are informational only — their exact value can be misread as a progress percentage.

**(c) `0.x` indefinitely.**
* Good, because it never has to make a stability promise.
* Bad, because it withholds a backward-compatibility signal indefinitely, which a tool with a stable output contract should eventually provide.

### Fork 4 — Version source of truth

**(a) Static in `pyproject.toml` + `importlib.metadata`. ✅ Chosen.**
* Good, because it is the ecosystem-standard single source plus standard-library runtime read.
* Good, because it requires no additional dependency and removes the hand-maintained attribute that previously drifted.
* Good, because all three observable version strings derive from one declaration.
* Bad, because each bump is a manual edit to the metadata field (accepted — it is the human gate from Fork 1).

**(b) Hand-maintained `__version__` in source.**
* Good, because `from codeograph import __version__` resolves directly with no indirection.
* Bad, because a code-resident version that must be kept in step with packaging metadata is exactly the duplicated-source pattern that drifted; the ecosystem is moving away from a hand-maintained attribute.
* Neutral, because it can read from metadata instead, which is option (a).

**(c) Version-control-tag derived.**
* Good, because the tag is the single source and between-tag builds receive automatic development versions.
* Good, because it removes manual version edits entirely.
* Bad, because it requires release-tagging discipline and version-control history at build time, which the v1 release flow does not yet establish.
* Neutral, because it can be adopted later without changing the runtime read.

## More Information

### Relationships

* **ADR-001** (project skeleton & configuration) — defines the CLI entry point and where the version is surfaced; this ADR removes the hand-maintained version attribute and routes `--version` through package metadata.
* **ADR-006** (knowledge graph schema) — owns the graph `schema_version`; under Fork 2 it independently governs graph-output compatibility.
* **ADR-022** (run manifest & structured logging) — records `codeograph_version` in the manifest; under Fork 4 that field is sourced from package metadata.
* **ADR-025** (manifest schema layout) — owns the manifest `schema_version`; under Fork 2 it independently governs manifest-output compatibility.

### Deferred items

* **Version-control-tag-derived versioning** (`setuptools-scm` / `hatch-vcs`) — adopt when a tagged release is cut per increment; migratable without changing the runtime read (Fork 4 option (c)).
* **Conventional-commit-driven automated bumps** — adopt if and when commit-level breaking-change marking is enforced, restoring reliability to an auto-derived bump (Fork 1 option (c)).

### References

* Semantic Versioning 2.0.0 — https://semver.org/spec/v2.0.0.html
* PEP 440 — Version Identification and Dependency Specification — https://peps.python.org/pep-0440/
* PEP 621 — Storing Project Metadata in `pyproject.toml` — https://peps.python.org/pep-0621/
* `importlib.metadata` — https://docs.python.org/3/library/importlib.metadata.html
* MADR template — https://github.com/adr/madr
