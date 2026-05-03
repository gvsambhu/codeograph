---
status: proposed
date: 2026-05-03
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-007 — Golden-Graph Pattern

## Context and Problem Statement

Codeograph's pipeline produces a knowledge graph as its central artefact (ADR-006). The deterministic half — AST extraction, complexity calculation, edge resolution — is supposed to produce byte-identical `graph.json` for the same input across runs. ADR-006's amendment pins canonical-form rules in the writer to make this true. ADR-007 pins how that property is *tested* in CI.

Without an automated regression harness, silent drift can slip in. A parser refactor might subtly change how Lombok-synthesised methods are named; a complexity calculator change might subtly alter scoring; an edge-resolver tweak might miss a class of references. None of these necessarily break unit tests, but each one degrades graph quality. The pattern that catches them — used by Babel, tree-sitter, rustc, TypeScript, ESLint and every other mature code-analysis tool — is **golden testing**: commit a known-good output for a pinned input, and re-run the pipeline against the input on every change to assert byte-equality.

ADR-007 pins eight decisions: which corpus or corpora to use, what scope of output is part of the golden contract, how comparison is performed, where goldens live and how they refresh, what test harness invokes them, what granularity goldens have, what CI cadence runs them, and what reproducibility envelope ensures the byte-equal property is achievable in practice.

The scope is narrow: this ADR covers regression testing of the deterministic half of the pipeline (`graph.json`). Correctness measurement (LLM-judge scorecards, structural quality checks) is owned by ADR-017. Renderer byte-stability is owned by ADR-019. LLM-prompt iteration testing is owned by ADR-014. ADR-007 sits between these as the deterministic-extraction guardrail.

## Decision Drivers

* **Catches unintended drift in the deterministic pipeline.** Primary purpose; everything else is secondary.
* **Aligns with ADR-006 canonical-form sha256 contract.** Same canonical bytes power both manifest integrity and golden assertions; one mechanism, two uses.
* **Surgical failure mode.** When a golden test fails, the dev should immediately know what kind of regression happened.
* **Industry-standard pattern.** Defensible in writing, recognisable to reviewers.
* **Low barrier to running locally.** A contributor should be able to run goldens with `pytest`, no special tooling.
* **Acceptable CI cost.** Public repo; free GitHub Actions tier covers expected volume.
* **Composable with future ADRs.** ADR-017 (eval framework), ADR-019 (snapshot tests), ADR-021 (determinism contract) extend in their own directions without conflict.
* **Stable across years.** A golden suite that requires constant maintenance defeats its purpose.

## Considered Options

Each fork below was evaluated against the drivers. Options that were considered and rejected appear in the Pros and Cons section at the end.

### Fork 1 — Corpus selection

* (a) Spring PetClinic (canonical small).
* (b) Spring PetClinic REST variant.
* (c) JHipster generated monolith.
* (d) Custom hand-built fixture only.
* **(e) Multi-corpus tiered (custom fixture + PetClinic; JHipster deferred to v1.1).** ✅

### Fork 2 — Scope of golden

* **(a) Graph only — `graph.json` deep-equal target.** ✅
* (b) Graph + LLM annotations with mocked / recorded LLM.
* (c) Graph + LLM annotations with live LLM and tolerance comparator.
* (d) Full pipeline (graph + LLM + rendered output).

### Fork 3 — Comparison strategy

* **(a) Byte-equal after canonical serialization.** ✅
* (b) Structural equality (parse JSON, compare as Python dicts).
* (c) Semantic equality with custom comparator and normalization pass.

### Fork 4 — Storage and update workflow

* **(a) Goldens committed to repo; refresh via `--update-goldens` flag.** ✅
* (b) Goldens generated on first run; CI fails if missing.
* (c) Goldens stored externally (LFS / S3); referenced by hash.

### Fork 5 — Test harness

* **(a) pytest fixture in `tests/test_golden.py`.** ✅
* (b) Standalone CLI subcommand (`codeograph test --golden`).
* (c) Standalone eval framework (`codeograph eval --suite golden`, ADR-017 territory).

### Fork 6 — Granularity

* **(a) One golden per corpus — final `graph.json` only.** ✅
* (b) Per-pipeline-stage goldens.
* (c) Per-class node goldens.

### Fork 7 — CI cadence

* (a) Every PR + every push to main, all corpora.
* (b) Nightly cron + on-demand for all corpora.
* (c) Tag-based, runs only on release tags.
* **Hybrid: (a) for Tier 1 + Tier 2 every PR; (b) for Tier 3 nightly (v1.1).** ✅

### Fork 8 — Reproducibility envelope

* (a) Trust the writer; no test-layer defence.
* (b) Test-layer normalization safety net (strip volatile fields).
* **(c) Reproducibility envelope (CI pins OS, Python, JDK, TZ, locale, hashseed).** ✅

## Decision Outcome

### Fork 1 — Corpus selection: (e) Multi-corpus tiered

Three tiers serve different purposes; v1 ships Tier 1 + Tier 2; Tier 3 is deferred to v1.1.

| Tier | Corpus | Path | Source | Why this corpus |
|---|---|---|---|---|
| **Tier 1** | `codeograph-corpus` | `tests/fixtures/codeograph-corpus/` | Project-owned hand-built fixture | Deterministic edge-case coverage: every Lombok annotation, every class kind (class/interface/enum/record/sealed/annotation), method overloads, inner/nested/anonymous classes, multi-module Maven setup, deliberate AST-fallback trigger |
| **Tier 2** | `spring-petclinic` | `tests/fixtures/spring-petclinic/` (git submodule) | `spring-projects/spring-petclinic` pinned to a release tag | Real-world Spring shape, reviewer recognition, integration sanity check |
| **Tier 3** (v1.1) | `jhipster-snapshot` | `tests/fixtures/jhipster-snapshot/` | Generated locally and committed | Scale and LLM cost characterisation; nightly only |

Tier 1 is the "edge cases we deliberately built." Tier 2 is the "would a reviewer's eye catch obvious wrongness?" Tier 3 is deferred — JHipster generation is documented in v1.1 work.

### Fork 2 — Scope of golden: (a) Graph only

`graph.json` is the deep-equal target. `llm-annotations.json` is **not** part of the golden contract — LLM output is non-deterministic by nature; byte-equal is meaningless. Renderer output is **not** part of the golden contract — covered by ADR-019 snapshot tests in v1.1.

The pipeline gains an `--ast-only` (or `--no-llm`) mode for test runs: Pass 1 / Pass 2 LLM passes are skipped entirely; `llm-annotations.json` is not emitted. This is a minimal pipeline-orchestration concern, flagged for the implementation phase.

### Fork 3 — Comparison strategy: (a) Byte-equal canonical

The test asserts byte equality of the canonical-form `graph.json`:

```python
def assert_golden(actual_path: Path, golden_path: Path) -> None:
    actual = actual_path.read_bytes()
    golden = golden_path.read_bytes()
    assert actual == golden, byte_diff(actual, golden)
```

Writer canonical-form rules (per ADR-006 amendment):

* `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
* trailing `\n` at EOF; LF line endings (enforced via `.gitattributes` `*.json text eol=lf`)
* nodes sorted by `id`; edges sorted by `(type, from, to)`
* node-property arrays (`implements`, `modifiers`, …) sorted before emission
* no wall-clock timestamps, run ids, or absolute filesystem paths in `graph.json`

The same canonical bytes power both this byte-equal assertion and the manifest's `sha256` integrity hash from ADR-006. One contract, two uses.

### Fork 4 — Storage and update workflow: (a) Repo-committed with refresh flag

Layout:

```
codeograph/
├── tests/
│   ├── fixtures/
│   │   ├── codeograph-corpus/        ← Tier 1 source (project-owned)
│   │   └── spring-petclinic/         ← Tier 2 source (git submodule, pinned tag)
│   ├── golden/
│   │   ├── codeograph-corpus/
│   │   │   └── graph.json            ← canonical-form, committed
│   │   └── spring-petclinic/
│   │       └── graph.json
│   ├── test_golden.py
│   └── conftest.py                   ← provides --update-goldens flag
```

Refresh workflow:

```
$ pytest tests/test_golden.py --update-goldens
$ git diff tests/golden/                  # reviewer sees diff
$ git add tests/golden/
$ git commit -m "test: refresh goldens after Lombok @Builder fix"
```

Refresh PRs should include a commit-message explanation of *why* goldens drift (informal convention, not enforced).

#### Adding a new corpus — checklist

When a future corpus (e.g., `spring-music`) joins:

| Step | Required? | Files touched |
|---|---|---|
| 1. Vendor source | Always | `tests/fixtures/<corpus>/`, possibly `.gitmodules` |
| 2. Pin version | Always | Submodule pointer or `PROVENANCE.md` |
| 3. Register in `CORPORA` parametrize list | Always | `tests/test_golden.py` |
| 4. Generate + inspect golden | Always | `tests/golden/<corpus>/graph.json` |
| 5. Document corpus | Always | `tests/fixtures/README.md` |
| 6. Commit | Always | git history |
| 7. CI submodule support | First submodule only | `.github/workflows/*.yml` |
| 8. Nightly schedule | First Tier 3 only | `.github/workflows/nightly.yml` |
| 9. NOTICE update | If license requires | `codeograph/NOTICE` |
| 10. Schema or parser changes | If new features exercised | ADR-006, ADR-003, schema files |

Steady state for a "more Spring of the same" corpus: 5 always-required steps, ~6 file touches, ~2 commits.

### Fork 5 — Test harness: (a) pytest fixture

```python
# tests/test_golden.py
import pytest
from pathlib import Path
from codeograph.cli import run_pipeline
from codeograph.testing.golden import assert_golden

CORPORA = [
    pytest.param("codeograph-corpus", id="custom-fixture"),
    pytest.param("spring-petclinic", id="petclinic"),
    # Tier 3 example (v1.1):
    # pytest.param("jhipster-snapshot", id="jhipster", marks=pytest.mark.tier3),
]

@pytest.mark.parametrize("corpus", CORPORA)
def test_golden_graph(corpus, tmp_path, golden_updater):
    fixture_dir = Path(f"tests/fixtures/{corpus}")
    out_dir = tmp_path / "out"
    run_pipeline(fixture_dir, out_dir, ast_only=True)

    actual_path = out_dir / "graph.json"
    golden_path = Path(f"tests/golden/{corpus}/graph.json")

    if golden_updater.enabled:
        golden_updater.write(golden_path, actual_path)
    assert_golden(actual_path, golden_path)
```

`conftest.py` provides the `--update-goldens` flag and `golden_updater` fixture. Failure reporting is pytest-native (full diff, traceback). IDE discoverability is automatic. CI integration is `pytest tests/test_golden.py -m "not tier3"` for PRs and `pytest tests/test_golden.py -m tier3` for nightly.

### Fork 6 — Granularity: (a) One golden per corpus

`tests/golden/<corpus>/graph.json` is the only golden file per corpus. Stage-level regressions are caught by per-component unit tests (`tests/unit/test_parser.py`, `tests/unit/test_complexity.py`, `tests/unit/test_lombok_synthesizer.py`); golden tests catch end-to-end drift. Per-class goldens are explicitly out of scope.

### Fork 7 — CI cadence: hybrid (a + b)

| Tier | Cadence | Workflow file | Selector |
|---|---|---|---|
| Tier 1 + Tier 2 | Every PR + push to main | `.github/workflows/ci.yml` | `pytest -m "not tier3"` |
| Tier 3 (v1.1) | Nightly + manual | `.github/workflows/nightly.yml` | `pytest -m tier3` |

Tier 3 nightly failures open a GitHub issue (via action) but do not block any specific PR. Manual re-trigger via `workflow_dispatch` is supported on both workflows.

PR workflow YAML excerpt:

```yaml
on:
  pull_request:
  push:
    branches: [main]

jobs:
  golden:
    runs-on: ubuntu-22.04
    env:
      TZ: UTC
      LC_ALL: C.UTF-8
      PYTHONHASHSEED: '0'
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - uses: actions/setup-java@v4
        with:
          java-version: '17.0.9'
          distribution: 'temurin'
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12.7'
      - run: pip install -e .[dev]
      - run: pytest tests/test_golden.py -m "not tier3"
```

### Fork 8 — Reproducibility envelope: (c)

The byte-equal contract assumes a stable runtime environment. CI pins every relevant variable:

| Component | Pin | Rationale |
|---|---|---|
| OS image | `ubuntu-22.04` | LTS base, stable until ~2027 |
| Python | `3.12.x` (minor pinned, patch flexible) | Minor bumps are safe; major bumps require ADR |
| JDK | `17.0.x` Temurin | Java 17 LTS; major bumps require ADR |
| JavaParser | from `pyproject.toml` | Single source of truth, already pinned per ADR-006 amendment |
| `TZ` | `UTC` | Removes locale-time surprises |
| `LC_ALL` | `C.UTF-8` | Locale-stable string sorting |
| `PYTHONHASHSEED` | `0` | Defence vs accidental hash-iteration dependence |

A test-side environment assertion runs first and aborts the run on drift:

```python
# tests/test_environment.py
def test_environment_pinned():
    assert javaparser_version() == required_javaparser_version(), (
        "JavaParser version drift would invalidate goldens"
    )
    assert sys.version_info >= (3, 12), "Python ≥3.12 required"
    assert os.environ.get("TZ") == "UTC", "TZ must be UTC"
    assert os.environ.get("LC_ALL", "").startswith("C.UTF-8"), "LC_ALL must be C.UTF-8"
    assert os.environ.get("PYTHONHASHSEED") == "0", "PYTHONHASHSEED must be 0"
```

Fail-fast on env drift saves debugging time; a contributor running `pytest` locally on an unpinned env sees a clear "your env doesn't match CI" message instead of a confusing golden-mismatch.

`CONTRIBUTING.md` will document the pinned versions and recommend `pyenv` (Python) and `sdkman` (JDK) for local matching.

### Pipeline orchestration constraint flagged for ADR-013

The pipeline must support an `--ast-only` (or `--no-llm`) mode: skip Pass 1 / Pass 2 LLM passes entirely; emit `graph.json` and `manifest.json` only; do not emit `llm-annotations.json`. This is a small surface — Pass 1 / Pass 2 just no-op — but it is a real CLI flag that ADR-013's LLM provider abstraction must accommodate. Flagged here for ADR-013 to honour.

## Consequences

**Positive.**

* Drift in the deterministic half of the pipeline is caught at PR time, not after merge.
* Reviewer sees graph diff inline in the PR — refresh PRs are auditable.
* Pytest-native failure reporting; no custom diff infrastructure to maintain.
* IDE-discoverable tests; one-click re-run during dev.
* Same canonical bytes power both manifest sha256 (ADR-006) and golden assertions — one contract, two uses.
* CI environment is pinned end-to-end; dependency or runtime drift cannot silently invalidate goldens.
* JavaParser / JDK / Python upgrades become explicit goldens-refresh events, not surprise CI failures.
* Tier 1 custom fixture provides edge-case coverage we own; Tier 2 PetClinic provides realism check.
* No coupling to internal pipeline stage boundaries — refactors don't churn goldens.
* Adding a new corpus is a documented 5-step checklist.
* Tier 3 (v1.1) integrates cleanly via `@pytest.mark.tier3` without burdening PR feedback.

**Negative.**

* CI must pin OS / Python / JDK / TZ / locale / hashseed; contributors who want to reproduce locally must match. Mitigated: documented in `CONTRIBUTING.md` with `pyenv` / `sdkman` pointers.
* Golden refresh PRs can have large diffs when an intentional change touches many classes (e.g., a complexity-formula tweak). Reviewer must inspect carefully. Mitigated: pre-commit hook can summarise the diff scope; refresh PRs should explain *why* in the commit message.
* JavaParser version upgrades force deliberate goldens refresh on every dep bump. Mitigated: pin in `pyproject.toml`; treat upgrades as explicit, reviewer-visible events (already noted in ADR-006 amendment).
* Tier 2 PetClinic submodule adds a small CI fetch overhead (~5 seconds with shallow clone). Acceptable.
* Custom fixture (Tier 1) requires hand-maintenance — adding a new edge case means adding source files. Acceptable; it's the cost of having edge-case control.
* Tier 3 nightly failures appear out of band (issue created by CI action); discipline required to triage promptly.
* `--ast-only` mode adds a small CLI surface to the pipeline; minor but real.

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. **Tier 1 fixture exists** — `tests/fixtures/codeograph-corpus/` contains hand-built source covering every Lombok annotation, every class kind, multi-module setup, fallback trigger.
2. **Tier 2 submodule pinned** — `tests/fixtures/spring-petclinic/` is a git submodule pointing at a specific release tag.
3. **Goldens committed** — `tests/golden/codeograph-corpus/graph.json` and `tests/golden/spring-petclinic/graph.json` are present and canonical-form.
4. **Pytest harness operational** — `pytest tests/test_golden.py` passes; failure shows pytest-native diff.
5. **`--update-goldens` flag works** — running with the flag refreshes goldens; running without it asserts.
6. **CI workflow YAML present** — `.github/workflows/ci.yml` runs Tier 1 + Tier 2; `.github/workflows/nightly.yml` placeholder exists for Tier 3.
7. **Environment pin assertions pass** — `tests/test_environment.py` runs and asserts env vars + tool versions.
8. **`--ast-only` mode operational in pipeline** — `run_pipeline(..., ast_only=True)` produces `graph.json` and `manifest.json` only.
9. **Refresh-PR exists in git history** — at least one demonstrative PR shows the refresh workflow (golden change + commit message explaining why).
10. **Adding-a-new-corpus checklist documented** — `tests/fixtures/README.md` includes the 10-step checklist.

## Pros and Cons of the Considered Options

### Fork 1 — Corpus selection

**(a) Spring PetClinic only.**
* Good, because canonical and recognisable.
* Good, because Apache 2.0, small, fast.
* Bad, because no multi-module exercise.
* Bad, because no Lombok / DTO / mapper / records — feature coverage too narrow.

**(b) Spring PetClinic REST.**
* Good, because closer to enterprise REST patterns.
* Good, because still recognisable and small.
* Bad, because still single-module; still no Lombok.

**(c) JHipster monolith only.**
* Good, because high feature density.
* Bad, because generated and repetitive — diff failures are noisy.
* Bad, because slow (5+ minutes) — wrong fit for every-PR.

**(d) Custom fixture only.**
* Good, because total edge-case control.
* Good, because we own the corpus permanently.
* Bad, because synthetic — reviewer cannot validate by intuition.

**(e) Multi-corpus tiered. ✅ Chosen.**
* Good, because Tier 1 (custom) gives edge-case control.
* Good, because Tier 2 (PetClinic) gives realism check and reviewer recognition.
* Good, because Tier 3 (JHipster, v1.1) handles scale separately without burdening PR feedback.
* Good, because matches industry pattern (tree-sitter, Babel, rustc all have multiple test corpora).
* Bad, because more files to maintain than (a) or (d) alone.
* Bad, because Tier 2 introduces a git submodule (small CI fetch overhead).

### Fork 2 — Scope of golden

**(a) Graph only. ✅ Chosen.**
* Good, because aligns with ADR-006 file-level determinism boundary.
* Good, because surgical failure mode — diff means "graph drift," nothing else.
* Good, because zero LLM cost in CI.
* Good, because byte-equal works without tolerance comparators.
* Bad, because LLM-prompt regressions and renderer regressions need separate test layers (ADR-017 / ADR-019).

**(b) Graph + recorded LLM.**
* Good, because catches LLM-prompt regressions.
* Bad, because heavy fixture maintenance; LLM fixtures invalidate on every prompt version change.
* Bad, because re-couples deterministic and probabilistic data ADR-006 deliberately split.

**(c) Graph + live LLM with tolerance.**
* Good, because end-to-end coverage.
* Bad, because flaky CI by construction.
* Bad, because real API spend per PR.

**(d) Full pipeline (graph + LLM + rendered).**
* Good, because one test catches everything.
* Bad, because conflates layers; failures are hard to triage.
* Bad, because rendered output is verbose — diffs become unreadable.

### Fork 3 — Comparison strategy

**(a) Byte-equal canonical. ✅ Chosen.**
* Good, because aligns with ADR-006 manifest sha256 contract.
* Good, because cheapest comparator (string equality).
* Good, because every byte difference is signal — no false negatives.
* Good, because failure shows exact byte position via standard diff tools.
* Bad, because writer must be canonical-form-disciplined (already required by ADR-006 amendment).

**(b) Structural equality (parsed dicts).**
* Good, because tolerates JSON whitespace and key-order variation.
* Bad, because breaks alignment with sha256 — same logical content with different byte layout produces different hashes.
* Bad, because still order-sensitive on arrays.

**(c) Semantic with normalization.**
* Good, because tolerates writer non-determinism (sort node/edge arrays at compare time).
* Bad, because hides writer regressions instead of surfacing them.
* Bad, because every new node/edge type may need new normalization rules.

### Fork 4 — Storage and update workflow

**(a) Goldens in repo, refresh via flag. ✅ Chosen.**
* Good, because PR diff shows actual content drift inline.
* Good, because zero network dependency for tests.
* Good, because industry-standard for code-tool goldens (Babel, tree-sitter, rustc, TypeScript, ESLint).
* Good, because explicit `--update-goldens` flag forces deliberate refresh moments.
* Bad, because repo grows linearly with each refresh (manageable at expected scale: ~1.5–6 MB/year).

**(b) Generated on first run.**
* Good, because no flag ceremony.
* Bad, because boundary between "intentional refresh" and "accidental refresh" is invisible.
* Bad, because risks silent rubber-stamping.

**(c) Externalised storage (LFS / S3).**
* Good, because minimal repo growth.
* Bad, because PR diff shows only hash change — reviewer cannot inspect content without fetching.
* Bad, because adds CI / dev dependencies on external storage.

### Fork 5 — Test harness

**(a) pytest fixture. ✅ Chosen.**
* Good, because pytest handles parametrisation, parallelism, diffing, JUnit output natively.
* Good, because IDE-discoverable; one-click re-run during dev.
* Good, because fits Python testing convention.
* Good, because no new CLI surface; doesn't pre-empt ADR-017's eval framework.
* Bad, because requires `pytest` available at dev/CI time (acceptable — already a dev dep).

**(b) Standalone CLI subcommand.**
* Good, because explicit user-facing command.
* Bad, because no real user case — golden tests are a developer activity, not a user activity.
* Bad, because reinvents pytest features (parametrisation, parallelism, diffing).

**(c) Standalone eval framework.**
* Good, because conceptually groups all "testing" things together.
* Bad, because pre-empts ADR-017's design before we've done it.
* Bad, because conflates regression testing with eval — different jobs, different right tools.

### Fork 6 — Granularity

**(a) One golden per corpus. ✅ Chosen.**
* Good, because aligns with ADR-006 schema artefact (`graph.json` is the schema'd output).
* Good, because no coupling to internal pipeline stage boundaries — refactors don't churn goldens.
* Good, because end-to-end coverage; the diff *is* the localisation.
* Good, because lowest file count; trivial to navigate and refresh.
* Good, because matches industry pattern.
* Bad, because diff inspection (briefly) needed to determine failure category — saved by per-component unit tests in `tests/unit/`.

**(b) Per-pipeline-stage goldens.**
* Good, because surgical stage-level localisation.
* Bad, because bakes internal pipeline structure into the test contract — refactors churn goldens.
* Bad, because duplicates what per-component unit tests already cover.

**(c) Per-class node goldens.**
* Good, because per-class regression visibility.
* Bad, because hundreds of files per corpus — file-tree noise, refactor PRs unreviewable.
* Bad, because no clear use case justifies the granularity.

### Fork 7 — CI cadence

**(a) Every PR + main, all corpora.**
* Good, because best merge-time safety; regressions cannot land in main.
* Good, because fast feedback for devs.
* Bad, because Tier 3 (5+ min) would slow PR feedback.

**(b) Nightly + manual, all corpora.**
* Good, because lowest CI cost.
* Bad, because regressions land in main and are caught later — quality of main suffers.
* Bad, because attribution requires bisecting up to a day's commits.

**(c) Tag-based, all corpora.**
* Good, because absolute minimum CI overhead.
* Bad, because regressions accumulate between releases.
* Bad, because misses the daily quality signal entirely.

**Hybrid: (a) Tier 1 + Tier 2 every PR; (b) Tier 3 nightly. ✅ Chosen.**
* Good, because cheap corpora gate every PR — main stays clean.
* Good, because expensive Tier 3 doesn't slow PR feedback.
* Good, because matches the actual cost/value of each tier.
* Good, because failure attribution stays trivial for Tier 1 + Tier 2.
* Bad, because two workflow files instead of one — small devops overhead.

### Fork 8 — Reproducibility envelope

**(a) Trust the writer.**
* Good, because lowest CI complexity.
* Bad, because environment drift (CI image upgrades, JDK / JavaParser bumps) flakes the suite without warning.

**(b) Test-layer normalization safety net.**
* Good, because tolerates accidental writer drift.
* Bad, because the *whole point* of byte-equal is to surface writer drift — silent absorption is the wrong direction.
* Bad, because conflicts with ADR-006 amendment contract.

**(c) Reproducibility envelope. ✅ Chosen.**
* Good, because aligns with and extends ADR-006 amendment.
* Good, because byte-equal becomes a reliable contract — no false negatives, no flakes from env drift.
* Good, because fail-fast environment assertions save debugging time.
* Good, because env upgrades become explicit, reviewer-visible refresh events.
* Bad, because contributors must match pinned env locally (mitigated: `pyenv` + `sdkman` documented in `CONTRIBUTING.md`).
* Bad, because CI YAML carries explicit pin lines — small ongoing maintenance.

## More Information

**Relationships to other ADRs.**

* **ADR-002** (input-agnostic + multi-module) is exercised by the Tier 1 custom fixture's two-module Maven setup.
* **ADR-003** (parsing strategy + Lombok synthesis) is exercised by both Tier 1 and Tier 2; failures here surface parser regressions.
* **ADR-004** (complexity model) — raw integer metrics live in graph nodes; drift catches metric-formula regressions.
* **ADR-005** (token utilization) — `--ast-only` mode skips Pass 1 / Pass 2 entirely; LLM contract is unaffected by golden testing.
* **ADR-006** (knowledge graph schema) is the test contract; the canonical-form rules from its amendment are the foundation of byte-equality.
* **ADR-013** (LLM provider abstraction) must support `--ast-only` mode — flagged here as an orchestration constraint.
* **ADR-017** (eval framework) is a sibling concern, not a parent — golden tests stay in pytest; eval framework owns correctness measurement.
* **ADR-018** (test strategy / pytest) — golden tests are one of the test categories under that ADR's umbrella.
* **ADR-019** (snapshot + negative tests, v1.1) extends the same byte-equal pattern to renderer output.
* **ADR-021** (determinism contract, v1.1) formalises the determinism guarantee; ADR-007 is a working example of the contract.
* **ADR-022** (run manifest + structured logging) — manifest is not part of golden contract (it carries timestamps and run ids by design).

**Deferred items.**

* Tier 3 JHipster corpus snapshot — committed in v1.1 once JHipster generator command is documented. Adds nightly cadence and `tier3` pytest marker.
* GitHub action that auto-creates a tracking issue when nightly Tier 3 fails — v1.1 polish.
* Pre-commit hook that summarises the scope of golden diffs in PR descriptions — v1.1 nice-to-have.
* `tests/golden-history/` archived snapshots for forensic comparison across schema versions — speculative; not in v1.

**References.**

* MADR (Markdown Architectural Decision Records) — https://adr.github.io/madr/
* Babel fixture testing — https://babeljs.io/docs/en/babel-helper-fixtures
* tree-sitter test corpus — https://tree-sitter.github.io/tree-sitter/creating-parsers#command-test
* rustc UI tests — https://rustc-dev-guide.rust-lang.org/tests/ui.html
* TypeScript baseline tests — https://github.com/microsoft/TypeScript/wiki/Writing-Compiler-and-Language-Service-Tests
* pytest parametrisation — https://docs.pytest.org/en/stable/how-to/parametrize.html
* pytest-snapshot pattern — https://github.com/joseph-roitman/pytest-snapshot
* GitHub Actions cron workflows — https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule
