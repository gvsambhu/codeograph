---
status: accepted
date: 2026-05-28
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-018 — Test Strategy with pytest

## Context and Problem Statement

The project's correctness story rests on a layered test surface: golden-graph regression for the deterministic half of the pipeline (ADR-007), eval-framework scorecards for graph and code quality (ADR-017), and unit + integration tests for the codebase itself (FR-19). Three of those layers have their own ADRs; this ADR locks the remaining one — the pytest layer that asserts on package internals, the conventions that govern it, and the CI shape that runs everything together.

FR-19 sets the floor: "pytest test suite at `tests/` with unit + integration tests; CI blocks merge on red; unit test coverage target ≥ 80% on `codeograph/`." That single sentence underspecifies seven decisions:

- Where do tests live? What separates a unit test from an integration test from an eval invocation from a golden run?
- Where do fixture corpora live? Are the example corpora reused as test fixtures, or do tests have their own corpora?
- What does the mock LLM provider look like? Does the test suite ever talk to a real provider?
- What does coverage actually measure? Line or branch? What's excluded? How does CI enforce the threshold?
- How are tests named and organized? Mirror the package layout, or group by feature?
- What does the CI workflow look like? Single OS or matrix? Single job or split? Which jobs gate merge?
- Which assertions in tests are byte-equal vs structural? Where is the determinism boundary?

The framework runs without depending on any live external service. CI uses no LLM API keys. Tests targeting cross-OS behaviour are reserved for a future amendment when contributor demand surfaces. Snapshot tests for mock-driven byte-stable rendered output are reserved for the future snapshot + negative tests ADR.

## Decision Drivers

* **Tractable v1 implementation** — seven forks produce a test layer that ships with two layers, three markers, six determinism helpers, one mock provider, and a five-job CI workflow. Bounded surface; no speculative infrastructure.
* **No silent failures** — `--cov-fail-under=80` hard-fails CI on threshold drop; failing scorecards exit non-zero from `codeograph eval`; failing tests block merge.
* **Determinism / determinism boundary clarity** — the artefact classification table makes every test author's choice mechanical (byte-stable vs structural vs not-asserted-directly).
* **SOLID-clean composition** — mock provider is test-only with no public-API commitment; helpers grow on demand; the test layer reads no internals of the eval CLI it tests via.
* **Forward compatibility with v1.1** — branch coverage, cross-OS CI matrix, provider-contract replay, snapshot infrastructure, and the formal determinism contract are all reserved with documented extension paths.
* **Citation discipline** — coverage threshold cites FR-19; mock provider failure types cite the `LlmProvider` ABC; the CI matrix extension procedure cites ADR-008's `PurePosixPath` and the encoding/line-ending disciplines added here.
* **Renderer ergonomics** (transferred to test-author ergonomics) — fixture lookup is mechanical from the path; new tests follow mirror layout; descriptive function names are searchable.
* **No external service dependency** — no Codecov, no live LLM, no remote fixture sources. CI runs without secrets in v1.

## Considered Options

### Fork 1 — Test layer boundaries

* (a) two layers (`tests/unit/` + `tests/integration/`); goldens and eval are not pytest (eval lives in CI workflow as `codeograph eval`).
* (b) three layers (unit + integration + eval-as-pytest).
* (c) four layers (unit + integration + goldens + eval, all pytest).
* **(d) two layers (a) plus three pytest markers (`slow`, `external`, `eval`); default `pytest` skips all three; goldens runner is one file in `tests/integration/`; eval runs as a CI workflow step via `codeograph eval`. ✅**

### Fork 2 — Fixture corpora policy

* (a) all committed under `tests/fixtures/<purpose>/`; example corpora are separate and not reused.
* (b) all committed; integration tests reuse example corpora as input.
* **(c) tiered — tiny fixtures under `tests/fixtures/<concern>/`; integration mini-corpora under `tests/fixtures/corpora/<corpus_id>/`; example corpora separate under `examples/`; a small set of `slow + external` smoke tests in `tests/integration/test_examples_smoke.py` invoke `codeograph run --ast-only` against example corpora. ✅**
* (d) generate fixtures at test time from declarative specs.

### Fork 3 — Mock LLM provider formalization

* (a) `MockLlmProvider` under `tests/`; minimal capability (canned responses + call inspection); no live-LLM tests in v1.
* (b) public `codeograph.testing.MockLlmProvider` API; richer capability; opt-in `live` marker gated by env var.
* **(c) test-only `MockLlmProvider` + small `MockLlmProviderBuilder` under `tests/fixtures/llm/`; minimal mock class composed via the builder; no live-LLM tests in v1; provider-contract replay deferred to v1.1. ✅**
* (d) test-only mock + separate `tests/integration/test_provider_contract.py` running against recorded-fixture replay.

### Fork 4 — Coverage tool and threshold semantics

* **(a) `pytest-cov` line coverage; single global 80% threshold matching FR-19; `--cov-fail-under=80` in CI; standard exclusions; terminal + HTML reports. ✅**
* (b) (a) plus branch coverage (`--cov-branch`).
* (c) per-package tiered thresholds (LLM = 90%, renderers = 80%, CLI = 70%) with global ≥ 80%.
* (d) (a) plus Codecov / Coveralls integration via XML report.

### Fork 5 — Test naming and organization convention

* (a) mirror `codeograph/` layout in `tests/unit/`; one `test_<module>.py` per source module; free functions; descriptive names.
* (b) feature-grouped throughout (one file per feature, multiple source modules per file).
* (c) mirror layout with class-grouped tests (`class TestClassSelector`).
* **(d) mirror `codeograph/` layout in `tests/unit/`; feature-grouped in `tests/integration/`; free functions throughout; descriptive `test_<unit>_<scenario>_<expected>` naming pattern; `@pytest.mark.parametrize` for shared-assertion-shape scenarios; class-grouping permitted only when shared `setup_method` is non-trivial. ✅**

### Fork 6 — CI integration shape

* (a) single monolithic workflow; single Python version; Linux only.
* **(b) split jobs by speed tier (`lint` / `unit` / `integration-external` / `eval` matrix / `report`); parallel where independent; Linux only; single Python; aggressive caching; `unit` job uses `strategy.matrix.os: [ubuntu-latest]` for extension hooks; `shell: bash` on every `run`; `.gitattributes * text=auto eol=lf`; `encoding="utf-8"` test-layer discipline. ✅**
* (c) (b) plus Python version matrix.
* (d) (b) plus OS matrix.

### Fork 7 — Determinism boundary in v1

* (a) classification table normative; no assertion helpers; per-test ad hoc.
* **(b) classification table normative + small `tests/helpers/determinism.py` with six helpers (`assert_byte_equal_except`, `assert_scorecard_structural`, `assert_compile_check_byte_equal`, `assert_log_contains`, `assert_iso8601`, `assert_sha256`); snapshot pattern reserved for ADR-019. ✅**
* (c) defer entirely to the formal determinism contract ADR (v1.1).
* (d) (b) plus a `tests/helpers/snapshot.py` stub reserving the snapshot pattern.

## Decision Outcome

### Fork 1 — Test layer boundaries: (d) two layers + three markers

Two test directories under `tests/`:

```
tests/
├── unit/                            # mirrors codeograph/ package layout
└── integration/                     # feature-grouped end-to-end flows
```

Three pytest markers registered in `pyproject.toml` (`[tool.pytest.ini_options]`):

| Marker | Definition | Default behaviour |
|---|---|---|
| `slow` | Any single test taking > 5 seconds even with mocks | Skipped by default |
| `external` | Requires `npx` / `tsc` / `mvn` / `go` on PATH | Skipped by default |
| `eval` | Invokes `codeograph eval` | Skipped by default; CI runs `codeograph eval` directly, not via pytest |

```toml
[tool.pytest.ini_options]
markers = [
    "slow: any single test > 5s with mocks",
    "external: requires npx / tsc / mvn / go on PATH",
    "eval: invokes codeograph eval (CI runs it directly, not via pytest)",
]
addopts = "-m 'not slow and not external and not eval'"
```

Default `pytest` (no args) runs the fast unit + non-marker integration suite. Heavier sweeps are explicit opt-in:

```bash
pytest                                              # fast inner-loop signal
pytest -m external                                  # requires Java + Node + Maven installed
pytest -m slow                                      # goldens runner
pytest -m "slow or external"                        # full local sweep
```

The goldens runner lives at `tests/integration/test_goldens.py` (single file walking `tests/goldens/<corpus_id>/`), marked `slow`. The eval framework invocation lives in the CI workflow (`codeograph eval examples/*/out`), not in pytest — it consumes the eval surface ADR-017 Fork 5 locked.

### Fork 2 — Fixture corpora policy: (c) tiered

Three locations, each for one purpose:

```
tests/
├── fixtures/
│   ├── parser/                     # tiny: single Java strings, synthetic graph nodes
│   ├── graph/
│   ├── render/
│   ├── eval/
│   └── corpora/                    # integration: mini Maven projects
│       ├── minimal_rest/
│       │   ├── pom.xml
│       │   └── src/main/java/.../...
│       ├── qdsl_persistence/
│       ├── lombok_dtos/
│       └── validation_heavy/
└── goldens/                        # ADR-007 reference artefacts
    └── spring-rest-sample/

examples/                           # ADR-017 Fork 7
├── spring-rest-sample/
└── spring-blog-api/
```

Example corpora are NOT loaded by unit tests. Integration tests load them only via the locked smoke-test pattern at `tests/integration/test_examples_smoke.py`:

```python
import pytest
from pathlib import Path

EXAMPLE_CORPORA = list(Path("examples").iterdir())

@pytest.mark.slow
@pytest.mark.external
@pytest.mark.parametrize("corpus_dir", EXAMPLE_CORPORA,
                         ids=lambda p: p.name)
def test_example_corpus_renders_cleanly(corpus_dir, tmp_path):
    """Asserts: codeograph run --ast-only completes, manifest validates,
    graph.json validates. Does NOT assert on specific class counts."""
    ...
```

v1 ships three or four integration mini-corpora under `tests/fixtures/corpora/`:

| Corpus | Cross-cutting concern |
|---|---|
| `minimal_rest` | One controller + service + repository; covers Forks 1-2 of ADR-010 |
| `qdsl_persistence` | QueryDSL custom repository → raw SQL tier; covers ADR-010 Fork 4 `db_layer` |
| `lombok_dtos` | `@Data`, `@Value`, `@Slf4j`, `@AllArgsConstructor`; covers ADR-010 Fork 8 Lombok intent-mapping |
| `validation_heavy` | DTOs with multiple JSR-380 decorators; covers ADR-010 Fork 7 |

Fixture file format discipline: Java sources as `.java` files (compilable as-is so parser tests get real input); graph snippets as `.json` validating against the schema; scorecard snippets as `.json` validating against the scorecard schema. No `.txt` blobs.

### Fork 3 — Mock LLM provider formalization: (c) test-only mock + builder

`MockLlmProvider` and `MockLlmProviderBuilder` live at `tests/fixtures/llm/mock_provider.py` and are loaded via `tests/conftest.py` as fixtures. No public API surface; no `codeograph.testing` namespace.

```python
# tests/fixtures/llm/mock_provider.py
from codeograph.llm import LlmProvider, CallContext, ProviderResponse

@dataclass
class MockLlmProvider(LlmProvider):
    """Test double. Records every call. Returns canned responses.

    Constructed via MockLlmProviderBuilder. Direct instantiation produces
    an empty mock that raises MockLlmProviderError on any call (fail loud).
    """
    responses: list[ProviderResponse] = field(default_factory=list)
    responses_by_prompt_hash: dict[str, ProviderResponse] = field(default_factory=dict)
    failures: dict[int, Exception] = field(default_factory=dict)  # call_index -> error
    calls: list[CallContext] = field(default_factory=list)

    async def complete(self, ctx: CallContext) -> ProviderResponse:
        call_idx = len(self.calls)
        self.calls.append(ctx)
        if call_idx in self.failures:
            raise self.failures[call_idx]
        if self.responses_by_prompt_hash:
            return self.responses_by_prompt_hash[ctx.prompt_content_hash]
        if self.responses:
            return self.responses.pop(0)
        raise MockLlmProviderError("no response configured")

class MockLlmProviderBuilder:
    """Compose mock scenarios without per-test subclassing."""
    def with_canned_response(self, content, usage=None): ...
    def with_response_sequence(self, responses: list[ProviderResponse]): ...
    def with_prompt_hash_response(self, content_hash: str, response: ProviderResponse): ...
    def with_failure_on_call(self, n: int, error: Exception): ...
    def build(self) -> MockLlmProvider: ...
```

**Assertion API:** tests inspect `mock.calls: list[CallContext]` post-run.

```python
def test_annotator_calls_provider_once_per_class(make_mock_provider, fixture_graph):
    mock = (MockLlmProviderBuilder()
            .with_response_sequence([fake_resp, fake_resp, fake_resp])
            .build())
    annotator = NodeAnnotator(mock, ...)
    await annotator.annotate(fixture_graph)
    assert len(mock.calls) == 3
    assert all(c.purpose == Purpose.ANNOTATE for c in mock.calls)
```

**Failure-injection error types** match production:

| Error | Test purpose |
|---|---|
| `RateLimitError` | Retry-policy backoff tests |
| `APIConnectionError` | Retry-policy reconnection tests |
| `APITimeoutError` | Timeout-handling tests |
| `APIStatusError` | Provider 5xx surface tests |

**No live-LLM tests in v1.** The `live` marker is not registered; no test imports a real provider; CI configures no LLM API keys. Release-time validation against a real provider is a manual smoke step documented in the developer section of the README — never automated in v1.

**Determinism contract:** mock outputs are byte-identical given identical builder method calls in identical order, with no use of OS time / random / thread id in test setup. This is the prerequisite for the future snapshot-test ADR.

### Fork 4 — Coverage tool and threshold semantics: (a) pytest-cov line, 80%, hard fail

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-m 'not slow and not external and not eval' --cov=codeograph --cov-report=term-missing --cov-report=html --cov-fail-under=80"

[tool.coverage.run]
source = ["codeograph"]
omit = [
    "*/_generated/*",                       # ADR-014 PromptId constants
    "codeograph/__main__.py",
]

[tool.coverage.report]
exclude_also = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@abstractmethod",
    "if __name__ == .__main__.:",
    "def __repr__",
    "pragma: no cover",
]
fail_under = 80
show_missing = true
```

**Line coverage only** in v1. Branch coverage is deferred to v1.1 with a case-driven trigger (a documented bug that branch would have caught and line did not).

**Coverage scope** is `codeograph/` minus the auto-generated PromptId constants directory and the trivial CLI entry point.

**Exclusion patterns** cover defensive blocks (`TYPE_CHECKING`, `NotImplementedError`, abstract methods, `__main__` guards, `__repr__`).

**Per-line `pragma: no cover`** opt-out is permitted with a comment explaining why; reviewed in PR like any other code change.

**CI failure** via `--cov-fail-under=80` (both in `addopts` and `[tool.coverage.report]` for belt-and-suspenders) — coverage erosion blocks merge immediately.

**Reports generated:** `term-missing` (CI log shows missed lines) and `html` (developer drill-down at `htmlcov/index.html`; `htmlcov/` is in `.gitignore`). No XML report in v1.

**New-package coverage discipline:** adding a new package to `codeograph/` requires unit tests bringing it within the 80% threshold; no exclusion-by-default.

**Threshold tightening process:** an ADR amendment raises the threshold only after a sustained period of the actual coverage clearing the new floor; no aspirational tightening. Loosening requires a superseding ADR (not an amendment) — loosening is structurally significant.

### Fork 5 — Test naming and organization: (d) mirror unit + feature-grouped integration

```
codeograph/                          tests/unit/
├── llm/                             ├── llm/
│   ├── provider.py                  │   ├── test_provider.py
│   └── retry.py                     │   └── test_retry.py
├── rendering/                       ├── rendering/
│   ├── class_selector.py            │   ├── test_class_selector.py
│   └── domain_grouping.py           │   └── test_domain_grouping.py
└── renderers/                       └── renderers/
    └── typescript_nestjs/               └── typescript_nestjs/
        ├── config.py                        ├── test_config.py
        └── renderer.py                      └── test_renderer.py

                                     tests/integration/
                                     ├── test_run_pipeline.py
                                     ├── test_render_pipeline.py
                                     ├── test_eval_pipeline.py
                                     ├── test_goldens.py
                                     └── test_examples_smoke.py
```

Unit tests mirror `codeograph/` package layout exactly — finding the test for `class_selector.py` is mechanical (`tests/unit/rendering/test_class_selector.py`). Integration tests are feature-grouped — finding "the render-pipeline tests" is mechanical (`tests/integration/test_render_pipeline.py`).

Free functions throughout; class-grouping permitted only when shared `setup_method` / `teardown_method` state is non-trivial (more than a one-liner). When a test class is used, no inheritance from a base test class (anti-pattern that fragments discoverability).

Descriptive function names:

```python
def test_class_selector_take_all_strategy_when_domain_smaller_than_cap(): ...
def test_class_selector_stratified_skips_empty_low_bucket_with_warning(): ...
def test_renderer_refuses_security_class_under_default_policy(): ...
def test_threshold_min_ratio_derives_skip_when_value_in_band_gap(): ...
```

Length up to ~80 characters acceptable. The function name is the primary documentation; docstrings are optional and added only when scenario context exceeds what the name carries.

`@pytest.mark.parametrize` is reserved for "same assertion, different inputs":

```python
@pytest.mark.parametrize(("cbo", "wmc", "expected"), [
    pytest.param(8, 3, "high",   id="or_high_cbo"),
    pytest.param(1, 4, "low",    id="and_low"),
    pytest.param(3, 10, "medium", id="else_medium"),
])
def test_bucket_classifier(cbo, wmc, expected):
    assert bucket({"cbo": cbo, "wmc": wmc}, THRESHOLDS) == expected
```

Each parametrize tuple gets an explicit `id` so failure messages are readable.

**Snapshot-style assertions are forbidden in `tests/unit/`** — goldens are ADR-007 territory and live in `tests/integration/test_goldens.py`; unit tests assert on explicit values.

**Async tests** use `pytest-asyncio` (already in the project's test deps); marked `@pytest.mark.asyncio` or covered by `asyncio_mode = "auto"`.

**Test independence:** no test depends on the side effect of another test. Fixtures default to `scope="function"`.

### Fork 6 — CI integration shape: (b) split jobs + extension hooks

`.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14", cache: "pip" }
      - shell: bash
        run: pip install -e ".[dev]"
      - shell: bash
        run: ruff check .
      - shell: bash
        run: ruff format --check .
      - shell: bash
        run: mypy codeograph

  unit:
    strategy:
      matrix:
        os: [ubuntu-latest]
        # To extend to Windows / macOS:
        # 1. Add 'windows-latest' and/or 'macos-latest' to the matrix above.
        # 2. Verify .gitattributes carries 'eol=lf' on text fixtures.
        # 3. Verify every test uses encoding='utf-8' explicitly on read_text/write_text.
        # 4. The 'integration-external' and 'eval' jobs intentionally stay Linux-only
        #    until a contributor needs cross-OS coverage of those layers.
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14", cache: "pip" }
      - shell: bash
        run: pip install -e ".[dev]"
      - shell: bash
        run: pytest --cov=codeograph --cov-fail-under=80

  integration-external:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14", cache: "pip" }
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "17", cache: "maven" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - shell: bash
        run: pip install -e ".[dev]"
      - shell: bash
        run: pytest -m external
      - shell: bash
        run: pytest -m slow

  eval:
    needs: [unit, integration-external]
    runs-on: ubuntu-latest
    strategy:
      matrix:
        corpus: [spring-rest-sample, spring-blog-api]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14", cache: "pip" }
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "17", cache: "maven" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - shell: bash
        run: pip install -e ".[dev]"
      - shell: bash
        run: codeograph run examples/${{ matrix.corpus }}/src --out /tmp/out --target ts
      - shell: bash
        run: codeograph eval /tmp/out
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: scorecards-${{ matrix.corpus }}
          path: /tmp/out/evals/

  report:
    needs: eval
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.14", cache: "pip" }
      - uses: actions/download-artifact@v4
        with: { pattern: "scorecards-*", path: ./scorecards/ }
      - shell: bash
        run: pip install -e ".[dev]"
      - shell: bash
        run: codeograph eval report ./scorecards/*/
      - uses: actions/upload-artifact@v4
        with:
          name: cross-corpus-report
          path: evals/cross-corpus-report.*
```

**All jobs gate merge** via the GitHub branch-protection rule on `main` listing every job as a required check; configured per `CONTRIBUTING.md`.

**Cross-OS extension procedure** (documented in the workflow file itself as the comment above the `unit` matrix):
1. Add `windows-latest` and/or `macos-latest` to the `unit.strategy.matrix.os` array.
2. Verify `.gitattributes` carries `eol=lf` on text fixtures (already locked here).
3. Verify every test uses `encoding="utf-8"` on `Path.read_text` / `Path.write_text` (already locked here).
4. `integration-external` and `eval` jobs intentionally remain Linux-only until contributor demand surfaces.

**Project-level disciplines locked by this fork** to make the extension mechanical:

- `.gitattributes` at repo root with `* text=auto eol=lf` so Windows checkouts preserve LF on text files.
- Every `Path.read_text` / `Path.write_text` in `tests/` passes `encoding="utf-8"` explicitly. Enforced by review; a future lint rule could mechanize the check.
- `shell: bash` on every workflow `run` step so commands work on Windows runners the day they land.

**No secrets configured.** The workflow does not reference `secrets.*` — no live LLM, no third-party services in v1.

### Fork 7 — Determinism boundary in v1: (b) classification table + helpers

The artefact-by-artefact classification table below is normative; it determines what kind of assertion every new test author writes:

| Artefact | Class | v1 assertion approach |
|---|---|---|
| `graph.json` (Pass 0 output) | **Byte-stable** | ADR-007 golden test asserts byte-equal canonical-form sha256 |
| Scaffold template output (`package.json`, `tsconfig.json`, `main.ts`, etc.) | **Byte-stable** | Unit test asserts byte-equal output for a Jinja2 template rendered against fixed metadata |
| `manifest.json` deterministic fields (`schema_version`, `scorecards.*.path`, `compile_checks.*.path`, `artefacts.*.path`) | **Byte-stable** | Unit / integration test asserts exact field values |
| `manifest.json` non-deterministic fields (`run_id`, `run_timestamp`, sha256 hashes of LLM-mediated artefacts) | **Structural** | Test asserts field presence and type via `assert_iso8601` / `assert_sha256`; not exact value |
| `evals/compile-checks.<target>.json` sidecar | **Byte-stable** | Unit test asserts byte-equal for a fixed renderer config; integration test asserts sha256 in manifest pointer matches |
| `evals/<kind>-scorecard.json` deterministic-check fields (`id`, `category`, `result`, `value`, `threshold`, `rationale`) | **Byte-stable** | Unit test against a fixture asserts exact `value` and derived `result` per check |
| `evals/<kind>-scorecard.json` per-run fields (`duration_ms`, `run_timestamp`, `corpus_id`) | **Structural / range** | Test asserts presence + sensible range (`duration_ms >= 0`, `run_timestamp` is ISO 8601) |
| `evals/<kind>-scorecard.json` skipped-slot fields (`semantic_accuracy`, `llm_judge`) | **Byte-stable** | Test asserts `result == "skip"`, `details.skip_reason == "deferred_v1.1"`, `details.owner_adr == "ADR-020"` |
| `out/<target>/<source>.ts` (LLM-rendered TypeScript) | **NOT byte-stable in v1** | No byte-equal test; integration test asserts file existence + `compile_checks` passes + contains expected decorators via AST or regex |
| `out/llm-annotations.json` | **NOT byte-stable in v1** | Unit test asserts schema validity + structural properties; no byte-equal |
| `out/telemetry/run-*.jsonl` | **Structural** | Test asserts per-record schema validity; not specific field values |
| `<cache_dir>/cache.db` content | **NOT asserted directly** | Indirect via `codeograph cache stats` output |
| `evals/cross-corpus-report.md` | **Structural** | Test asserts markdown table presence + expected check ids in rows + expected corpus ids in columns; not exact cell content |
| `evals/cross-corpus-report.json` deterministic fields | **Byte-stable** | Test asserts exact aggregation for a fixture |
| Log output (console / file) | **NOT asserted as content** | Test captures via `caplog` and asserts on `record.message` substrings via `assert_log_contains`; never exact log format |

Six helpers in `tests/helpers/determinism.py`:

```python
# tests/helpers/determinism.py
def assert_byte_equal_except(actual: dict, expected: dict,
                              *, ignore_keys: list[str]) -> None: ...
def assert_scorecard_structural(actual: dict, *, kind: str) -> None: ...
def assert_compile_check_byte_equal(actual: dict, expected_checks: list[dict],
                                     *, ignore_renderer_version: bool = True) -> None: ...
def assert_log_contains(caplog, message_substring: str,
                         *, level: int = logging.INFO) -> None: ...
def assert_iso8601(value: str) -> None: ...
def assert_sha256(value: str, *, length: int = 64) -> None: ...
```

Helpers contribute to the 80% coverage gate. New helpers added only when a real pattern repeats across three or more tests; never speculatively.

`ignore_keys` operates on top-level keys only in v1; nested-key removal (e.g., `jq`-style paths) added in a future amendment if the pattern emerges.

### Constraint flagged for ADR-019 (snapshot + negative tests, v1.1)

Mock-driven byte-stable rendered output is the snapshot pattern this ADR explicitly reserves. ADR-019 will:
- Add a new helper module `tests/helpers/snapshot.py`.
- Add a new directory `tests/snapshots/<corpus>/<target>/` parallel to `tests/goldens/`.
- Extend the artefact classification table above with a new row: "rendered TypeScript under mock-driven snapshot — **byte-stable** when invoked through the snapshot harness."
- Inherit Fork 3's mock-provider determinism contract as the substrate.

### Constraint flagged for ADR-021 (determinism contract, v1.1)

The classification table here is the test-layer boundary. ADR-021's contract is the consumer-guarantees layer — what fields downstream tools (external CI, dashboards, badge generators) can rely on being byte-stable across runs. The two ADRs do not overlap. ADR-021 will reference this table as the v1 baseline and extend it with per-field consumer guarantees.

### Constraint flagged for ADR-008 / ADR-017

The encoding (`encoding="utf-8"`) and line-ending (`.gitattributes eol=lf`) disciplines locked in Fork 6 are project-level. Any future code or template that reads / writes text files outside `tests/` must follow the same discipline — surfaced as a code-review checklist item, not enforced by a separate ADR.

## Consequences

**Positive.**
1. Test author choice is mechanical: where (mirror layout vs feature-grouped per Fork 5), what kind (the classification table per Fork 7), how (the marker default + selective opt-in per Fork 1), how to assert (the six helpers per Fork 7).
2. CI fast-fail visible in roughly 30 seconds for lint errors; full test sweep under 5 minutes with cold caches; near-instant on warm caches.
3. Coverage erosion is mechanically blocked at the 80% gate; per-line opt-out (`pragma: no cover`) requires a comment and survives PR review.
4. The mock provider supports retry / concurrency / failure-injection tests through composition; no per-test subclassing.
5. The CI workflow is extensible to multi-OS by adding one array entry — the disciplines that make this work (`shell: bash`, `encoding="utf-8"`, `.gitattributes eol=lf`) are already locked.
6. Snapshot-test infrastructure is cleanly reserved for the future ADR; no premature stubs or half-implementations.
7. Test-layer determinism boundary is explicit per artefact, not negotiated per test.
8. Fixture corpora at three locations each serve one purpose (tiny fixtures, integration mini-corpora, public example corpora) without cross-contamination.

**Negative.**
1. Three pytest markers and two test layers and three fixture-corpora locations mean four conventions to internalize before writing a first test — documented in `CONTRIBUTING.md`.
2. Default `pytest` skipping `slow`/`external`/`eval` means CI must explicitly opt-in to those markers — discipline-dependent; a misconfigured CI workflow could silently miss those tests.
3. The 80% coverage threshold is judgment — could be too loose (misses real gaps) or too tight (drives ceremony tests); recalibration is a documented amendment process.
4. No live-LLM tests in v1 means provider drift could ship to users — partially mitigated by manual release-time smoke; v1.1 provider-contract replay is the structured fix.
5. Linux-only CI means cross-OS bugs surface for the first time in user reports — the discipline ladder mitigates the common cases (paths, encoding, line endings) but does not catch all.
6. Three or four integration mini-corpora plus two example corpora plus the goldens corpora add committed repo weight; the trade is real test signal per corpus.
7. Per-line `pragma: no cover` opt-out can be abused — review discipline catches it but it is a soft enforcement.
8. The classification table will need additions as new artefacts are introduced; the additive amendment process is documented but is friction.

## Confirmation

1. Running `pytest` (no args) on a clean clone with `pip install -e ".[dev]"` completes in under 60 seconds and prints a coverage report showing ≥ 80% line coverage on `codeograph/` (verified by a CI workflow step that fails if either condition is not met).
2. Running `pytest -m external` on a machine with `npx`, `tsc`, and `mvn` on PATH completes without error; running it on a machine without them fails the preflight check inside the test (verified by an integration test that conditionally skips).
3. Running `pytest -m slow` invokes the goldens runner; modifying a committed golden's sha256 by one byte causes the goldens test to fail with a clear "byte-equal mismatch" message (verified by an integration test that intentionally tampers with a fixture golden in a temp dir).
4. Importing `MockLlmProvider` from `tests/fixtures/llm/mock_provider.py` and constructing one via `MockLlmProviderBuilder().with_canned_response(content="...").build()` produces a mock whose `complete()` returns the canned response and records the call in `mock.calls` (verified by a unit test).
5. Constructing `MockLlmProvider()` directly (empty) and calling `complete()` raises `MockLlmProviderError("no response configured")` (verified by a unit test).
6. The `tests/helpers/determinism.py` module exports exactly six helpers (`assert_byte_equal_except`, `assert_scorecard_structural`, `assert_compile_check_byte_equal`, `assert_log_contains`, `assert_iso8601`, `assert_sha256`); each has at least one unit test in `tests/unit/test_helpers.py` (verified by importing and asserting on `dir(...)` plus the unit test coverage report).
7. `pyproject.toml` registers exactly three markers (`slow`, `external`, `eval`); `addopts` carries `-m 'not slow and not external and not eval'`; running pytest with any unregistered marker fails per pytest config (verified by a CI workflow step).
8. `.github/workflows/ci.yml` defines exactly five jobs (`lint`, `unit`, `integration-external`, `eval`, `report`); the `unit` job uses `strategy.matrix.os: [ubuntu-latest]`; the `eval` job uses `strategy.matrix.corpus: [spring-rest-sample, spring-blog-api]`; the `report` job has `needs: eval` (verified by a YAML-validation test or a CI lint-of-workflow step).
9. `.gitattributes` at repo root contains the line `* text=auto eol=lf` (verified by a one-line CI check or repo-state assertion).
10. Running `grep -r "read_text\|write_text" tests/` shows every match is followed within the same call by `encoding="utf-8"` (verified by a periodic repo-state audit, or a future custom lint rule).
11. Coverage on `codeograph/` measured by `pytest --cov=codeograph` excludes lines matching the locked `exclude_also` patterns (`if TYPE_CHECKING:`, `@abstractmethod`, etc.) (verified by a unit test that introduces a `raise NotImplementedError` line and asserts it does NOT lower coverage).
12. A test asserting against an artefact in the "byte-stable" column of the classification table uses one of `assert_byte_equal_except`, `assert_compile_check_byte_equal`, or raw equality (verified by code review; a future custom lint rule could mechanize this).

## Pros and Cons of the Considered Options

### Fork 1 — Test layer boundaries

**(a) two layers; eval via CLI.**
* Good, because two clear layers — easy to know where to put a test.
* Good, because eval-as-CLI honors ADR-017 Fork 5's locked invocation surface.
* Good, because coverage cleanly measured on unit + integration; eval doesn't pollute.
* Bad, because eval-failure visibility in CI depends on workflow discipline.

**(b) three layers; eval-as-pytest.**
* Good, because eval invocations gated by pytest — one command for all eval validation.
* Bad, because duplicates ADR-017 Fork 5's invocation surface.
* Bad, because eval runtime wedged into pytest makes `pytest` slow.
* Bad, because coverage on `tests/eval/` doesn't add unit coverage signal.

**(c) four layers all pytest.**
* Good, because maximum separation.
* Bad, because goldens-as-pytest is thin over `codeograph run --ast-only`.
* Bad, because four directories is ceremony — contributors guess between integration and goldens.

**(d) two layers + three markers. ✅ Chosen.**
* Good, because honors ADR-017 Fork 5 — eval via CLI, not pytest wrapper.
* Good, because coverage measurement stays clean (default invocation skips heavy markers).
* Good, because default `pytest` stays fast.
* Good, because external-tool-dependent tests opt-out by default — locally runnable without Node.
* Good, because two directories + markers gives sharper separation than three+ directories.
* Bad, because three markers are conventions to learn — documented in `CONTRIBUTING.md`.

### Fork 2 — Fixture corpora policy

**(a) all committed under `tests/fixtures/`; no example reuse.**
* Good, because complete separation; tests don't depend on examples.
* Good, because test fixtures stay scoped to test needs.
* Bad, because duplication of effort — every integration test needs a fixture.
* Bad, because integration test fixtures may drift from "what a real Spring project looks like."

**(b) reuse example corpora.**
* Good, because zero duplication.
* Good, because a renderer regression that breaks the example is caught by tests too.
* Bad, because tight coupling — every example change potentially breaks tests.
* Bad, because example corpora are user-facing demos; test pressure degrades their signal.

**(c) tiered + smoke. ✅ Chosen.**
* Good, because test-scoped fixtures keep the test layer in control of its inputs.
* Good, because example corpora stay clean for demo purpose.
* Good, because smoke tests against examples catch demo-breaking regressions inside pytest.
* Good, because mirrors the established `tests/goldens/<corpus_id>/` convention.
* Bad, because three discovery paths (`tests/fixtures/`, `tests/goldens/`, `examples/`) — mitigable by clear naming.
* Bad, because slightly more committed Java code than option (b).

**(d) generate at test time.**
* Good, because test data lives next to the test — no fixture-file hunting.
* Bad, because generator surface is non-trivial to build and maintain.
* Bad, because generator drift from the real schema is a class of bug committed fixtures avoid.
* Bad, because does not address integration / corpus-scale fixtures.

### Fork 3 — Mock LLM provider formalization

**(a) tests/ minimal mock; no live.**
* Good, because test-only — no public API surface.
* Good, because no live-LLM surface in v1.
* Bad, because authors needing more capability subclass per test — fragmentation.

**(b) public `codeograph.testing` + live marker.**
* Good, because public test-utility surface for future external contributors.
* Good, because capability set covers retry/concurrency without subclassing.
* Bad, because exporting a public testing API commits to its stability.
* Bad, because `live` marker creates secret-management surface even gated by env.
* Bad, because capability creep — mock grows into its own product.

**(c) tests/ minimal mock + builder; no live. ✅ Chosen.**
* Good, because test-only — no public API commitment.
* Good, because builder composes capabilities without per-test subclassing.
* Good, because failure injection lives in the builder, not in every test fixture.
* Good, because no live-LLM tests in v1 — no secret-management surface, no per-test cost.
* Good, because deterministic mock outputs are the substrate for the future snapshot ADR.
* Bad, because the builder is one more class to document.

**(d) (a) + replay contract tests.**
* Good, because catches provider-contract breakage without live calls.
* Bad, because recording / replay machinery is its own dependency and skill set.
* Bad, because recorded fixtures go stale; refresh becomes ceremony.
* Neutral, because layered on top of (a) — addable as v1.1.

### Fork 4 — Coverage tool and threshold semantics

**(a) line, global 80%, cov-fail-under. ✅ Chosen.**
* Good, because matches FR-19 verbatim.
* Good, because standard exclusions match the project's defensive-code patterns.
* Good, because HTML report lets developers drill into specific uncovered lines.
* Good, because `--cov-fail-under=80` makes CI hard-fail on threshold drop.
* Good, because per-line `pragma: no cover` opt-out for genuine cases.
* Bad, because single global threshold may let well-covered subsystems mask under-covered ones.

**(b) line + branch.**
* Good, because catches "if was tested but else was not" bugs.
* Bad, because FR-19 says line coverage; branch is an extension.
* Bad, because branch coverage on straight-line code inflates the denominator.
* Bad, because adds noise to the report.

**(c) per-package tiered thresholds.**
* Good, because critical paths held to higher bars.
* Good, because low-priority paths not artificially padded.
* Bad, because maintenance overhead — per-package config drifts.
* Bad, because pytest-cov does not natively support per-package thresholds.
* Bad, because tiered thresholds invite politics.

**(d) (a) + Codecov.**
* Good, because PR comments showing coverage delta — immediate reviewer feedback.
* Good, because historical coverage trend visible.
* Bad, because external-service dependency (Codecov is a SaaS).
* Bad, because adds CI workflow surface and a service to vouch for.

### Fork 5 — Test naming and organization

**(a) mirror layout; free functions.**
* Good, because "where's the test for X.py?" mechanical.
* Good, because free functions match pytest idiom.
* Good, because parametrize ergonomics natural.
* Bad, because integration tests crossing modules don't have a natural single file.

**(b) feature-grouped.**
* Good, because each test file reads as a coherent feature story.
* Good, because fewer files overall.
* Bad, because "where's the test for X.py?" no longer mechanical.
* Bad, because refactor propagation breaks silently.

**(c) class-grouped tests.**
* Good, because grouping is explicit in code.
* Bad, because `self` ceremony for free-function-like tests.
* Bad, because class-based grouping breaks parametrize ergonomics slightly.
* Bad, because invites inheritance — anti-pattern.

**(d) mirror unit + feature-grouped integration. ✅ Chosen.**
* Good, because each layer's convention matches its purpose.
* Good, because free functions stay idiomatic pytest.
* Good, because descriptive names are searchable.
* Good, because parametrize reserved for shared-assertion-shape scenarios.
* Good, because class-grouping permitted as the escape hatch when shared setup is non-trivial.
* Bad, because two conventions to learn, but each lives in its own directory.

### Fork 6 — CI integration shape

**(a) monolithic.**
* Good, because one workflow file; easy to read.
* Bad, because every step waits for the previous.
* Bad, because no fast-feedback signal.

**(b) split + extension hooks. ✅ Chosen.**
* Good, because lint failure visible in ~30s.
* Good, because per-corpus matrix on eval; failure isolated.
* Good, because aggressive caching cuts cold-cache CI from minutes to seconds.
* Good, because `eval` depends on `unit` + `integration-external` (wasted-cost avoidance).
* Good, because matrix syntax + extension hooks enables one-line multi-OS extension later.
* Good, because cross-corpus report runs after eval, uploads markdown as CI artefact.
* Bad, because more YAML to maintain than a monolith.

**(c) + Python version matrix.**
* Good, because catches version-specific bugs.
* Bad, because 3× the unit job's runtime budget.
* Bad, because project pins 3.14 per ADR-001; supporting older not a stated goal.

**(d) + OS matrix now.**
* Good, because catches OS-specific bugs immediately.
* Bad, because Windows + macOS runners are slow and minute-billed.
* Bad, because most cross-OS bugs caught by `pathlib` / `PurePosixPath` discipline.
* Bad, because Java + Node tooling add OS complexity for marginal v1 value.

### Fork 7 — Determinism boundary in v1

**(a) classification table only; no helpers.**
* Good, because trivial — no new infrastructure.
* Good, because authors use familiar pytest / json / sha256 patterns.
* Bad, because repeated `data.pop("run_timestamp")` boilerplate.
* Bad, because inconsistent assertion styles across tests.

**(b) classification table + six helpers. ✅ Chosen.**
* Good, because classification table + helpers cover the common patterns.
* Good, because consistent assertion style across tests.
* Good, because helpers grow only when a real pattern repeats across 3+ tests.
* Good, because snapshot infrastructure reserved for ADR-019 cleanly.
* Bad, because one new directory (`tests/helpers/`) — small, scoped.
* Bad, because helpers themselves need unit coverage.

**(c) defer entirely to formal contract ADR.**
* Good, because no v1 work.
* Bad, because the boundary problem is in the test layer; the formal contract is for consumer guarantees — different scope.
* Bad, because test suite becomes inconsistent immediately.

**(d) (b) + snapshot stub.**
* Good, because same as (b).
* Bad, because stubs invite "while we're here, let me implement just a little" creep.
* Bad, because documenting snapshot in a Python stub before its ADR exists is upside-down.

## More Information

### Relationships

* **ADR-001** (project skeleton) — Python 3.14 pin; `pyproject.toml` is the config substrate; AI-permitted boilerplate covers CI YAML and test scaffolding.
* **ADR-003** (parsing strategy) — JDK 17+ requirement consumed by the CI `setup-java` step; `external` marker for tests requiring JDK.
* **ADR-006** (knowledge graph schema) — canonical-form sha256 substrate for the byte-stable classification of `graph.json`.
* **ADR-007** (golden-graph pattern) — `tests/goldens/<corpus_id>/` is the locked path; goldens runner lives in `tests/integration/test_goldens.py`.
* **ADR-008** (pluggable renderer interface) — `PurePosixPath` discipline in renderer return shape; scaffold templates produce byte-stable output (classification table).
* **ADR-009** (rendering budget cap) — `SelectionResult` is byte-stable when produced from a deterministic input.
* **ADR-010** (Spring → TS/NestJS mapping) — `TypeScriptConfig` field set determines what unit tests assert against; the `db_layer` / `unsupported_feature_policy` / `webflux_policy` matrix gets fixture coverage in `tests/fixtures/corpora/`.
* **ADR-013** (LLM provider abstraction) — `LlmProvider` ABC is the base for `MockLlmProvider`; `RateLimitError` / `APIConnectionError` / `APITimeoutError` / `APIStatusError` are the failure-injection types.
* **ADR-014** (prompt versioning) — `prompt_content_hash` is the substrate for prompt-hash-keyed mock responses.
* **ADR-015** (telemetry + response cache) — telemetry timestamps, cache hit timestamps, run ids are in the "structural / not byte-stable" rows of the classification table.
* **ADR-017** (evaluation framework) — `codeograph eval <output-dir>` is the eval invocation surface; ADR-018 runs it as a CI workflow step (not a pytest wrapper); the `eval` marker reflects this boundary; the scorecard schema validity tests + threshold-derivation tests live in `tests/unit/evals/`.

### Deferred items

* **Branch coverage (`--cov-branch`)** — triggered by either (a) sustained ship of v1 with line coverage not catching a real bug branch would have, or (b) a documented bug case where branch would have caught.
* **Cross-OS CI matrix (Windows + macOS)** — triggered by a contributor PR from a Windows / macOS user surfacing an OS-specific bug, or by a user-reported "fails on my OS" issue. The extension procedure is locked in the workflow comment.
* **Provider-contract replay tests** — triggered by a provider-API drift incident that the mock did not catch.
* **`live` marker for opt-in real-LLM tests** — introduced by ADR-020 when LLM-judge calibration needs live validation; the env-var gating, cost cap, and CI secret discipline are locked there.
* **Snapshot infrastructure (`tests/helpers/snapshot.py`, `tests/snapshots/<corpus>/`)** — owned by the future snapshot + negative tests ADR (v1.1); the mock-provider determinism contract here is the substrate.
* **Formal determinism contract / consumer guarantees** — owned by the future determinism contract ADR (v1.1); extends the artefact classification table from this ADR.
* **`tests/helpers/determinism.py` additional helpers** — added only when a real pattern repeats across 3+ tests; never speculatively.
* **`jq`-style nested-key support in `assert_byte_equal_except`** — added when the top-level-key limitation surfaces in a real test.
* **`ruff` plugin or custom check enforcing `encoding="utf-8"` discipline** — added if review-time enforcement proves insufficient.

### Open Questions / Future Work

* Will the 80% global coverage threshold prove too loose (subsystems mask gaps) or too tight (drives ceremony tests)?
* Will the marker discipline (`slow` / `external` / `eval`) stay meaningful, or will the categories blur as new tests are added?
* Will the mock provider builder API churn as new test scenarios surface, or stabilize quickly?
* Will the three or four integration mini-corpora prove sufficient, or will every new feature add another corpus?
* Will the CI minute consumption hit a budget concern as the eval matrix expands beyond two corpora?
* Will `external`-marker job duration outgrow the `unit` job, suggesting further split?
* Will the classification table need frequent additions, suggesting a more general assertion-policy mechanism?
* Will the first Windows / macOS contributor's PR surface OS-specific bugs the discipline ladder did not catch?

### References

* pytest documentation — https://docs.pytest.org/
* `pytest-cov` documentation — https://pytest-cov.readthedocs.io/
* `coverage.py` documentation — https://coverage.readthedocs.io/
* GitHub Actions documentation — https://docs.github.com/en/actions
* MADR template — https://github.com/adr/madr
