---
status: accepted
date: 2026-05-28
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-017 — Evaluation Framework

## Context and Problem Statement

The deterministic half of the pipeline (parse → graph → goldens) is validated by ADR-007's byte-equal regression tests. The probabilistic half (LLM annotation → corpus synthesis → render) needs a different validation surface — one that measures whether the graph and rendered output meet documented quality bars and produces a reviewable artefact that can sit in the README alongside the project's headline claims.

The functional requirements name the contract: seven graph-quality checks (FR-7a) and three code-quality checks per target (FR-7), each producing per-target scorecards (FR-9) recording exact model versions (FR-18, A4) and prompt versions (FR-15). The plan §2 freezes the output paths as `evals/graph-scorecard.json`, `evals/ts-scorecard.json`, `evals/go-scorecard.json`. None of these inputs specifies *how* checks compute their values, *how* thresholds embed, *how* the framework is invoked, or *how* multi-corpus aggregation produces the README's side-by-side view.

This ADR locks all of those — scorecard schema, threshold model, per-check operationalization for ten checks, eval invocation surface, compile-check execution policy, multi-corpus aggregation, and the manifest export of compile-check metadata that lets eval run decoupled from the renderer package.

The framework runs entirely on deterministic inputs in v1. The two LLM-mediated check slots (`semantic_accuracy` and `llm_judge`) are reserved structurally so v1 scorecards read as complete seven-check graph + three-check code tables, but their implementation is deferred to the LLM-judge calibration ADR (v1.1).

## Decision Drivers

* **Citation discipline** — every threshold cites its rationale (FR-12 / ADR-004); no subjective letter grades, no numbers from memory.
* **Determinism / determinism boundary clarity** — every v1 check is deterministic-or-explicitly-skipped; the band gap on `coverage` is the only soft state and it is opt-in by the threshold-shape opt-out.
* **No silent failures** — `skip` is a distinct first-class state from `pass` and `fail`; preflight failures (missing tool) and band-gap failures (`fail_below < value < pass_at_or_above`) both record actionable `details.skip_reason`.
* **SOLID-clean composition** — eval consumes a saved output dir; never imports renderer internals; never re-instantiates renderers at eval time. The decoupling makes external CI replay possible.
* **Forward compatibility with v1.1** — the `ScoreBandThreshold` discriminator is reserved for the LLM-judge calibration ADR; a new `test_coverage` slot ID can be added additively for the snapshot-tests ADR.
* **Tractable v1 implementation** — eight forks of design produce a framework that runs every v1 check with zero LLM cost and is testable on a deterministic fixture corpus.
* **Readability as a curated artefact** — scorecards are the visible deliverable of the entire quality story; their JSON shape, markdown rendering, and side-by-side cross-corpus view are designed for direct README integration.
* **YAGNI** — auto-install of compile-check tools, suite config files, fail-fast flags, CI freshness gates for the cross-corpus report, and committed markdown scorecard files are all explicitly deferred with documented v1.1 triggers.
* **Industry-standard pattern / reviewer recognition** — separate scorecard files + manifest pointers, two-phase manifest write, content-addressed sha256 tamper-evidence, `report` subcommand mirroring cache-report — all reuse patterns already in the codebase.

## Considered Options

### Fork 1 — Scorecard schema and storage shape

* **(a) three separate scorecard files under `evals/<kind>-scorecard.json`; manifest carries `{path, sha256, overall}` pointers per kind. ✅**
* (b) one unified `evals/scorecard.json` with `graph` and `targets.<name>` sections.
* (c) embedded directly inside `manifest.json` (no separate scorecard file).
* (d) separate files plus a top-level `scorecard-index.json` aggregator.

### Fork 2 — Threshold model and check-result semantics

* (a) single boolean `result` per check; no `value`, no `threshold` object (contradicts Fork 1's locked schema; listed for completeness).
* (b) tiered letter grade per check (`A`/`B`/`C`/`D`/`F` with grade-band thresholds).
* **(c) discriminated-union `threshold` per check kind (`BooleanThreshold`, `MinRatioThreshold`, `MaxCountThreshold`, `ScoreBandThreshold`); `result` mechanically derived from `(value, threshold)`. ✅**
* (d) flat `threshold: dict[str, Any]` with check-specific keys.
* (e) (c) plus an explicit `display` field per check for README rendering hints.

### Fork 3 — Seven graph-quality checks (FR-7a operationalization)

* **(a) lock all seven definitions exactly as proposed; six deterministic, `semantic_accuracy` reserved as `skip` owned by ADR-020 (v1.1). ✅**
* (b) lock only the names + value types + thresholds; algorithm details deferred to module-level documentation.
* (c) (a) plus a warn-only window on `relationship_correctness` and `internal_consistency` for the first eval cycle.
* (d) drop `semantic_accuracy` from v1 scorecard entirely; reintroduce as a new check id in v1.1.

### Fork 4 — Three code-quality checks per target (FR-7 operationalization)

* **(a) lock all three slots exactly as proposed; v1 ships `compile` (aggregating ADR-008's CompileCheck list) + `coverage` (feature coverage derived from ADR-010 Fork 9 audit + matrix); `llm_judge` reserved as `skip` owned by ADR-020. ✅**
* (b) lock `compile` and `llm_judge` as proposed; mark `coverage` as `skip` entirely until v1.1.
* (c) lock `compile` as proposed; redefine `coverage` as render coverage (compile_pass / selected).
* (d) add a fourth slot `feature_coverage` distinct from `coverage`; defer `coverage` to v1.1 (contradicts FR-7's exactly-three-checks specification).

### Fork 5 — Eval invocation surface

* (a) dedicated `codeograph eval <output-dir>` subcommand only; user composes render-then-eval manually.
* (b) auto-run after `codeograph run`; `--no-eval` flag to suppress.
* (c) separate `python -m evals` script, outside the `codeograph` package.
* **(d) `codeograph eval <output-dir>` subcommand AND `codeograph run --eval` opt-in sugar. ✅**

### Fork 6 — Compile-check execution policy

* (a) sequential within target, sequential across targets, fail-fast within target, no cleanup policy.
* (b) parallel across targets, sequential within target, continue-on-failure within target, no cleanup policy.
* (c) parallel everywhere (across targets AND within target).
* **(d) (b) plus explicit cleanup policy (default leave; `--clean` opt-in) plus never-auto-install tool policy. ✅**

### Fork 7 — Multi-corpus support shape

* (a) single corpus per `codeograph eval` invocation; CI loop drives the matrix; no aggregation command in v1.
* (b) multi-corpus invocation in one call; eval reads a `suite.yaml` config.
* **(c) single-corpus invocation (Fork 5) plus separate `codeograph eval report <output-dir...>` for cross-corpus aggregation; JSON + markdown outputs; v1 ships two committed corpora. ✅**
* (d) (c) plus committed markdown report + CI freshness gate.

### Fork 8 — Manifest export of `compile_checks`

* (a) embed inline in `manifest.json` as a top-level `compile_checks` field.
* **(b) sidecar files per target (`evals/compile-checks.<target>.json`); manifest carries `compile_checks.<target>: {path, sha256}` pointers; pin at render time. ✅**
* (c) re-resolve at eval time by re-instantiating the renderer (rejected — breaks the decoupling Fork 5 promised).
* (d) (b) plus acknowledgement that the sidecar lives inside the committed example dirs.

## Decision Outcome

### Fork 1 — Scorecard schema: (a) three separate files + manifest pointers

Each of the three scorecard kinds (graph + per-target code) lives in its own JSON file under `<output-dir>/evals/`. The manifest carries one pointer per scorecard:

```json
// manifest.json (additive — schema 1.3.0)
{
  "schema_version": "1.3.0",
  "scorecards": {
    "graph": { "path": "evals/graph-scorecard.json",
               "sha256": "<hash>",
               "overall": "pass" },
    "ts":    { "path": "evals/ts-scorecard.json",
               "sha256": "<hash>",
               "overall": "pass" }
  }
}
```

Each scorecard file follows the same shape:

```json
// evals/graph-scorecard.json
{
  "schema_version": "1.0.0",
  "kind": "graph",
  "corpus_id": "spring-rest-sample",
  "run_timestamp": "2026-05-28T14:32:11Z",
  "run_id": "<from manifest>",
  "reproducibility": {
    "codeograph_version": "0.4.0",
    "seed": 0
  },
  "checks": [ /* see Fork 2 for per-check record shape */ ]
}
```

Per-check record fields (locked across all checks; some always null for deterministic checks):

```python
class CheckResult(BaseModel):
    id: str                                        # snake_case; matches FR-7a/FR-7 vocabulary
    category: Literal["graph", "code"]
    result: Literal["pass", "fail", "skip"]       # derived per Fork 2
    value: bool | float | int | None              # None for skip
    threshold: Threshold                          # discriminated union per Fork 2
    rationale: str                                # cites source paper / ADR / FR row
    model_version: str | None                     # None for deterministic checks
    prompt_id: str | None
    prompt_content_hash: str | None
    duration_ms: int
    details: dict[str, Any]
```

Scorecard schema sources live in Python (`codeograph/evals/scorecard_schema.py`); the auto-generated JSON Schema is committed at `codeograph/evals/scorecard.schema.json` so external consumers (CI dashboards, badge generators) can validate against it without importing the Python package.

### Fork 2 — Threshold model: (c) discriminated-union with mechanical result derivation

Four threshold kinds; three populated in v1; one reserved for v1.1.

```python
from typing import Literal, Annotated, Union
from pydantic import BaseModel, Field

class BooleanThreshold(BaseModel):
    kind: Literal["boolean"]
    expected: bool                          # almost always True

class MinRatioThreshold(BaseModel):
    kind: Literal["min_ratio"]
    pass_at_or_above: float                 # ∈ [0, 1]
    fail_below: float | None = None         # None == sharp cutoff at pass_at_or_above

class MaxCountThreshold(BaseModel):
    kind: Literal["max_count"]
    pass_at_or_below: int                   # almost always 0
    fail_above: int | None = None

class ScoreBandThreshold(BaseModel):        # reserved for v1.1 LLM-judge ADR
    kind: Literal["score_band"]
    pass_at_or_above: float
    fail_below: float

Threshold = Annotated[
    Union[BooleanThreshold, MinRatioThreshold,
          MaxCountThreshold, ScoreBandThreshold],
    Field(discriminator="kind"),
]
```

**Result derivation rules (locked in implementation, not in JSON):**

| Threshold kind | `result == "pass"` iff | `result == "fail"` iff | `result == "skip"` iff |
|---|---|---|---|
| `BooleanThreshold` | `value == expected` | `value != expected` | (not produced from value) |
| `MinRatioThreshold` | `value >= pass_at_or_above` | `value < fail_below` (when set) | sharp + value below threshold OR band gap (`fail_below <= value < pass_at_or_above`) — `details.skip_reason: "band_gap"` |
| `MaxCountThreshold` | `value <= pass_at_or_below` | `fail_above` set AND `value > fail_above` | band gap (`pass_at_or_below < value <= fail_above`) — `details.skip_reason: "band_gap"` |
| `ScoreBandThreshold` | `value >= pass_at_or_above` | `value < fail_below` | band gap |

**Overall derivation per scorecard:** `overall = "pass"` iff every check has `result == "pass"`; `skip` results do not fail overall; any `fail` produces `overall = "fail"`.

**Skip-reason taxonomy:** `details.skip_reason ∈ {"band_gap", "preflight_missing_tool", "deferred_v1.1", "target_not_rendered", "source_path_unavailable", "no_v1_translatable_features_in_corpus", "no_golden_committed", "compile_checks_sidecar_missing_or_corrupt"}`.

### Fork 3 — Seven graph-quality checks: (a) lock all seven definitions exactly

All seven check definitions are normative; six run in v1; one reserved.

| Id | Threshold | Value | Computation | Deterministic? |
|---|---|---|---|---|
| `structural_completeness` | `MinRatioThreshold(pass_at_or_above=1.0)` | `float ∈ [0,1]` | `(class+method+field nodes emitted) / (declarations in source)` | ✅ |
| `relationship_correctness` | `MinRatioThreshold(pass_at_or_above=1.0)` | `float ∈ [0,1]` | `resolved_edges / (total_edges - unresolved_call_edges)` | ✅ |
| `schema_validity` | `BooleanThreshold(expected=True)` | `bool` | `graph.json` validates against `codeograph/schema/graph.schema.json` | ✅ |
| `internal_consistency` | `MaxCountThreshold(pass_at_or_below=0)` | `int ≥ 0` | count of invariant violations across (a) node id uniqueness within kind, (b) class references valid package, (c) method's parent class exists, (d) every ADR-009 domain non-empty, (e) `unresolved_call` edges have origin + target FQCN | ✅ |
| `semantic_accuracy` | `ScoreBandThreshold(pass_at_or_above=null, fail_below=null)` | `float ∈ [0,1]` when v1.1 populates | reserved — owned by ADR-020 (LLM-judge calibration, v1.1) | LLM-mediated; v1 ships `result: "skip"`, `details: {skip_reason: "deferred_v1.1", owner_adr: "ADR-020"}` |
| `reproducibility` | `BooleanThreshold(expected=True)` | `bool` | rerun `codeograph run --ast-only` against the recorded source path three times; compare canonical-form sha256 of each run's `graph.json` | ✅ (deterministic across 3 runs is the assertion) |
| `golden_graph_agreement` | `BooleanThreshold(expected=True)` | `bool` | current `graph.json` canonical-form sha256 matches `tests/goldens/<corpus_id>/graph.json`; reuses ADR-007 machinery | ✅ |

**Cost note for `reproducibility`:** runs Pass 0 three times → ~3× AST cost, zero LLM cost. Triggered only by `codeograph eval`, never by `codeograph run`. `--skip-check reproducibility` is the documented opt-out for fast inner-loop eval.

**Per-check rationale strings cite source ADRs and FR rows** (per FR-12 / ADR-004 citation discipline). Adding a new graph-quality check bumps `graph-scorecard.schema_version` (e.g., `1.0 → 1.1`) additively; removing a check requires a superseding ADR. JSON canonicalization sorts the `checks` array lexicographically by `id` for byte-stability.

### Fork 4 — Three code-quality checks per target: (a) lock all three slots

Slot 1 — `compile`. Aggregates ADR-008's `compile_checks()` list per Fork 6's execution policy. Result aggregation rule:

| All-CompileChecks state | Slot result | Slot value |
|---|---|---|
| All pass | `"pass"` | `1.0` |
| Any fail (mix of pass/fail) | `"fail"` | `pass_count / total_count` |
| All preflight-skip | `"skip"` (`band_gap` n/a) | `null`; `details.skip_reason: "preflight_missing_tool"` |
| Mixed pass + preflight-skip | `"pass"` iff every check that *ran* passed | `pass_count / ran_count`; `details.skipped_checks: [...]` |

| Field | Value (v1 TS) |
|---|---|
| `kind` | `MinRatioThreshold` |
| `pass_at_or_above` | `1.0` (sharp) |
| `rationale` | "FR-7 — compile is the minimum bar for generated code; ADR-008 Fork 3 supplies the per-renderer check list; aggregation is sharp because any failure indicates a renderer bug." |
| `details on fail/pass` | `details.check_results: [{name, cmd, exit_code, stdout_tail, stderr_tail, duration_ms}]` for each `CompileCheck` (stdout/stderr tail = last 100 lines; full output in sidecar log file) |

Slot 2 — `coverage`. Feature coverage derived from ADR-010 Fork 9 audit + matrix:

```
encountered = {distinct Spring annotations + framework patterns observed
               in selected classes' source}
v1_translatable     = encountered ∩ {ADR-010 Fork 9 matrix v1 row}
v1_actually_emitted = v1_translatable - {dropped under stub_todo}
                                      - {features in refused classes}
value = |v1_actually_emitted| / |v1_translatable|
```

| Field | Value (v1 TS) |
|---|---|
| `kind` | `MinRatioThreshold` |
| `pass_at_or_above` | `0.95` |
| `fail_below` | `0.85` (band gap → `result: "skip"` with `details.skip_reason: "band_gap"` and tightening note) |
| `rationale` | "ADR-010 Fork 9 coverage matrix defines what v1 promises to translate. The 95% sharp-pass bar holds the tool to its own published matrix; the 85% floor catches systemic regressions while the band signals a corpus with unusual annotation density needing human review." |
| `details on skip (empty denominator)` | `details.skip_reason: "no_v1_translatable_features_in_corpus"` |

Slot 3 — `llm_judge`. Reserved as `skip` in v1, owned by ADR-020.

```json
{
  "id": "llm_judge",
  "category": "code",
  "result": "skip",
  "value": null,
  "threshold": { "kind": "score_band", "pass_at_or_above": null, "fail_below": null },
  "rationale": "Deferred to ADR-020 (LLM-judge calibration, v1.1).",
  "model_version": null,
  "prompt_id": null,
  "prompt_content_hash": null,
  "details": { "skip_reason": "deferred_v1.1", "owner_adr": "ADR-020" }
}
```

**v1.1 `test_coverage` extension path:** when the future snapshot-tests ADR adds rendered-test generation, a separate check id `test_coverage` appends to the code-quality scorecard (additive `code-scorecard.schema_version: 1.0 → 1.1`). The `coverage` slot keeps feature-coverage semantics permanently.

### Fork 5 — Eval invocation surface: (d) subcommand + opt-in sugar

Primary surface:

```bash
codeograph eval <output-dir>                     # default: all scorecards
codeograph eval <output-dir> --scorecard graph   # only graph-quality
codeograph eval <output-dir> --scorecard ts      # only TS code-quality
codeograph eval <output-dir> --check reproducibility       # only one check
codeograph eval <output-dir> --skip-check reproducibility  # skip the expensive one
```

`--check` and `--skip-check` are mutually exclusive. Selecting `--scorecard` runs every check in that scorecard; `--check` runs only the named check across whichever scorecards contain it.

Opt-in sugar:

```bash
codeograph run <source> --out <out> --eval
# Equivalent to: codeograph run <source> --out <out> && codeograph eval <out>
```

Exit-code contract: `0` iff every selected scorecard's `overall == "pass"`; non-zero otherwise. `skip` results do not affect the exit code. `codeograph run --eval` exit code is the OR of render and eval — render failure OR eval failure produces non-zero.

Re-eval is idempotent: re-running `codeograph eval` overwrites `evals/*-scorecard.json` and patches the manifest pointer sha256. No `--force` flag required.

Missing output directory: exit code 2 with the message `"no rendered output at <path>; run \`codeograph run\` first."`. Missing per-target subdirectory: that target's code-scorecard skips with `details.skip_reason: "target_not_rendered"`; does not fail.

### Fork 6 — Compile-check execution policy: (d) parallel + continue + no-cleanup + no-install

Concurrency model:

```python
# pseudocode
with ThreadPoolExecutor(max_workers=len(selected_targets)) as pool:
    for target_results in pool.map(eval_one_target, selected_targets):
        record(target_results)

def eval_one_target(target):
    results = []
    for check in load_compile_checks_sidecar(target).checks:
        if not all_tools_present(check.required_tools):
            results.append(skip(check, reason="preflight_missing_tool"))
            continue
        results.append(run_with_timeout(check, timeout_s=120))   # continue regardless of result
    return results
```

| Concern | Policy |
|---|---|
| Across targets | Parallel (ThreadPoolExecutor; bounded by number of selected targets) |
| Within target | Strict iteration of the sidecar's `checks` list order |
| On check failure | Continue with the next check in the same target |
| Per-check timeout | 120 seconds (default); on timeout: `result: "fail"`, `details.timeout: true` |
| Total-job timeout | None at framework level; outer CI job timeout is the guard |
| Tool installation | Never. Preflight via `shutil.which(tool)`; missing → `skip` |
| Cleanup | Default: leave all artefacts in place. `--clean` removes `node_modules/` and any `CompileCheck.cleanup_paths` (future v1.1 field; ignored in v1 if absent) |
| Output capture | `stdout_tail`/`stderr_tail` last 100 lines embedded in `details.check_results[]`; full output written to sidecar `evals/<kind>-scorecard.compile.<check_name>.log` regardless of pass/fail |
| Per-check console log prefix | `[eval/<target>/<check_name>]` |
| Subprocess environment | Inherit parent env unchanged; no scrubbing |
| Working directory | Per-CompileCheck `workdir` resolved relative to `<output-dir>/<target>/` |

### Fork 7 — Multi-corpus support: (c) single-corpus eval + `eval report`

Per-corpus eval stays single output-dir per Fork 5. Cross-corpus aggregation lives in a separate subcommand:

```bash
codeograph eval report <output-dir> [<output-dir> ...] \
    [--output-json evals/cross-corpus-report.json] \
    [--output-md evals/cross-corpus-report.md]

# Typical CI usage:
for d in examples/*/out; do codeograph eval "$d"; done \
  && codeograph eval report examples/*/out \
       --output-md docs/scorecards-summary.md
```

**Per-kind aggregation rules:**

| Threshold kind | Aggregation across N corpora |
|---|---|
| `BooleanThreshold` | Report `pass_count / N` |
| `MinRatioThreshold` | Report mean, min, max of `value` across corpora |
| `MaxCountThreshold` | Report sum and max of `value` across corpora |
| `ScoreBandThreshold` (v1.1) | Same as `MinRatioThreshold` |

**Cross-corpus overall:** `pass` iff every corpus has every scorecard `overall == "pass"`; `fail` if any corpus has any scorecard `overall == "fail"`; `mixed` otherwise.

**Markdown table shape:** rows = checks; columns = corpora; cells = `pass ✅ / fail ❌ / skip ➖` + value where applicable. One table per scorecard kind (graph, ts, go).

Exit code: `0` iff cross-corpus overall is `pass`; non-zero otherwise.

**v1 shipped corpora:**

| Corpus | Purpose |
|---|---|
| `examples/spring-rest-sample/` | Synthetic, minimal; exercises the v1-translated subset of the Spring matrix (FR-9 minimum) |
| `examples/spring-blog-api/` | Broader; exercises persistence (JPA + QueryDSL), validation (`@Valid`), and configuration (`@ConfigurationProperties`) — cross-cuts ADR-010 Forks 4/6/7 |

Each ships with committed source, `out/` directory (graph + annotations + manifest + scorecards), and the `evals/compile-checks.<target>.json` sidecars. Committed scorecards become PR-diff visible — scorecard regressions appear as normal code review surface.

### Fork 8 — Manifest export of `compile_checks`: (b) sidecar files + manifest pointers, pinned at render time

The renderer's resolved `compile_checks()` list is written to a sidecar file at render time; the manifest carries a pointer.

```
out/
├── manifest.json
├── graph.json
├── llm-annotations.json
├── ts/
│   └── (rendered source files)
└── evals/
    ├── compile-checks.ts.json
    ├── graph-scorecard.json     ← written by `codeograph eval`
    └── ts-scorecard.json        ← written by `codeograph eval`
```

```json
// evals/compile-checks.ts.json
{
  "schema_version": "1.0.0",
  "target": "ts",
  "renderer_version": "0.4.0",
  "checks": [
    {
      "name": "tsc",
      "cmd": ["npx", "tsc", "--noEmit", "--strict"],
      "workdir": ".",
      "required_tools": ["npx"],
      "pass_on_exit_codes": [0]
    }
  ]
}
```

```json
// manifest.json (additive — schema 1.4.0)
{
  "schema_version": "1.4.0",
  "scorecards": { /* per Fork 1 */ },
  "compile_checks": {
    "ts": { "path": "evals/compile-checks.ts.json", "sha256": "<hash>" }
  }
}
```

**Write order at render time:** sidecar written first; manifest pointer + sha256 written after. Two-phase write matches DC2's `cache_stats` pattern.

**Read order at eval time:** (1) read manifest; (2) for each selected target, read manifest's `compile_checks.<target>.path`; (3) verify sha256; (4) parse the sidecar's `checks` list; (5) run per Fork 6's execution policy.

**Re-resolve fallback explicitly rejected.** If the sidecar is missing or sha256 mismatches, the `compile` slot result is `skip` with `details.skip_reason: "compile_checks_sidecar_missing_or_corrupt"`. Eval does not import the renderer package to recover. This preserves the determinism property — the `cmd` that runs is the `cmd` that was pinned at render time.

**`renderer_version` field** is recorded for audit; eval ignores it but external replay scripts can warn on drift. Schema-version evolution is additive; eval accepts unknown future fields with a warning.

### Constraint flagged for ADR-008

The `compile_checks` sidecar pattern locked here is the trigger ADR-008 Fork 3 deferred. ADR-008's "manifest export deferred" subsection should be cross-referenced from any future amendment that adds optional fields to `CompileCheck` (e.g., the `cleanup_paths` field flagged in Fork 6's belt-and-suspenders). Additions bump the sidecar's `schema_version`, not the manifest's.

### Constraint flagged for ADR-020 (LLM-judge calibration, v1.1)

Two slots reserved for ADR-020: `semantic_accuracy` in the graph scorecard and `llm_judge` in every code scorecard. Both ship in v1 with `result: "skip"` and the `ScoreBandThreshold` discriminator pre-allocated. ADR-020 fills in `pass_at_or_above` and `fail_below`, the calibration set, and the judge prompt. No scorecard schema change required when ADR-020 lands.

### Constraint flagged for ADR-019 (snapshot + negative tests, v1.1)

The `coverage` slot keeps feature-coverage semantics permanently. When rendered-test generation lands, a new check id `test_coverage` appends to the code-scorecard (additive schema bump `1.0 → 1.1`). The threshold kind for `test_coverage` will likely be `MinRatioThreshold` (line coverage); the discriminated-union schema does not need to expand.

## Consequences

**Positive.**
1. Every scorecard reads as a complete table — six deterministic graph checks plus one reserved-skip slot, two code-quality slots plus one reserved-skip slot. No mystery missing rows.
2. Every threshold has a cited rationale linking to a source ADR or FR row — no numbers from memory, no subjective letter grades.
3. Eval is decoupled from the renderer package — `codeograph eval <output-dir>` works on any saved output dir, on any machine with the right tooling, regardless of which codeograph version is installed. External CI replay is possible without `pip install codeograph`.
4. The discriminated-union threshold model accommodates four shapes (boolean, ratio, count, score band) without per-check special casing.
5. `skip` semantics distinguish "we ran it and the value is between fail and pass" (band gap) from "we couldn't run it" (preflight missing) from "this is reserved for a future ADR" (deferred). Three actionable categories instead of one.
6. Manifest stays minimal — `scorecards` and `compile_checks` are both pointer fields with sha256 tamper-evidence; the manifest never embeds full check records or full scorecard payloads.
7. Cross-corpus aggregation is a first-class command (`codeograph eval report`) with both JSON and markdown outputs; README integration is a re-run, not a hand-edit.
8. Compile-check execution is parallel-across-targets and continue-on-failure-within-target — both failures of a multi-check target surface in a single eval run.

**Negative.**
1. Eight forks produce a framework with substantial surface area — contributors building eval-adjacent tooling must read more before producing their first change.
2. The 95% / 85% feature-coverage band is a judgment call calibrated against the v1 shipped corpora; tightening or loosening requires an ADR amendment and is friction.
3. Reproducibility check's 3× AST cost makes eval substantially slower than a single render — `--skip-check reproducibility` is documented but easy to forget.
4. Two committed corpora (`spring-rest-sample` + `spring-blog-api`) plus their committed `out/` directories add repository weight; every renderer change that touches translation surface forces a scorecard refresh on both.
5. The discriminated-union Pydantic shape adds one concept (the `kind` discriminator) to the scorecard schema that external consumers must learn — slightly heavier than a flat dict.
6. The `compile_checks` sidecar adds one small file per rendered target — minor directory-listing noise.
7. The re-resolve fallback is explicitly rejected — a corrupt or missing sidecar produces a `skip` and an opaque user experience until they re-render. Documented but real.
8. Auto-installation of compile-check tools is never attempted — eval on a machine without `npx` skips the `compile` slot with a preflight message; new users have to read the eval section of the README before their first scorecard.

## Confirmation

1. Running `codeograph eval out/` against an output directory produced by `codeograph run` writes `out/evals/graph-scorecard.json` and `out/evals/ts-scorecard.json`; both files validate against `codeograph/evals/scorecard.schema.json` (verified by an integration test with a fixture corpus).
2. The `manifest.json` in the same output directory after eval contains a `scorecards` object with `graph` and `ts` keys, each holding `{path, sha256, overall}` (verified by JSON-schema validation test).
3. The `manifest.json` produced by `codeograph run` contains a `compile_checks.<target>: {path, sha256}` field for every rendered target; sha256 matches the actual file hash (verified by integration test).
4. Pydantic discriminated-union round-trip test: a `CheckResult` with `MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85)` and `value=0.92` serializes to JSON and deserializes back to the same Python object; `result` is `"skip"` (band gap) with `details.skip_reason == "band_gap"` (verified by unit test).
5. Running `codeograph eval out/ --scorecard graph` writes only `evals/graph-scorecard.json` and does NOT touch any `<target>-scorecard.json` files; the exit code reflects only the graph scorecard's overall (verified by integration test).
6. Running `codeograph eval out/ --skip-check reproducibility` produces a graph scorecard whose `reproducibility` check has `result: "skip"` and `details.skip_reason: "explicit_skip"`; total runtime is ≤ 0.4× of a full eval on the same fixture (verified by integration test asserting both fields and a runtime upper bound).
7. Running `codeograph eval out/` against a fixture where `tsc` is on PATH and source compiles produces `ts-scorecard.json` with `compile` slot result `"pass"`, `value: 1.0`, and `details.check_results[0].name == "tsc"` (verified by integration test).
8. Running `codeograph eval out/` against a fixture where `npx` is NOT on PATH produces `ts-scorecard.json` with `compile` slot result `"skip"`, `details.skip_reason == "preflight_missing_tool"`, `details.missing_tools == ["npx"]` (verified by integration test that temporarily renames `npx`).
9. Running `codeograph eval report examples/spring-rest-sample/out examples/spring-blog-api/out --output-md /tmp/x.md` writes a markdown file containing one table per scorecard kind (graph, ts) with rows for each check id and columns for each corpus (verified by integration test asserting markdown structure).
10. Modifying `out/evals/compile-checks.ts.json` after `codeograph run` (sha256 drifts from the manifest pointer) causes `codeograph eval out/` to record the `compile` slot as `"skip"` with `details.skip_reason: "compile_checks_sidecar_missing_or_corrupt"` (verified by integration test that intentionally tampers with the sidecar).
11. Mypy/pyright accept a hypothetical new `CheckResult` with `threshold = BooleanThreshold(expected=True)` and reject `threshold = {"kind": "boolean", "expected": "yes"}` (verified by a type-error fixture).
12. Running `codeograph eval` against an output directory whose `manifest.json.source_path` no longer resolves on disk produces `graph-scorecard.json` with `reproducibility` skipped (`details.skip_reason == "source_path_unavailable"`) and other six graph checks running normally (verified by integration test).

## Pros and Cons of the Considered Options

### Fork 1 — Scorecard schema and storage shape

**(a) three separate files + manifest pointers. ✅ Chosen.**
* Good, because matches the plan §2 path layout exactly — no drift from the freeze-point snapshot.
* Good, because manifest stays minimal — pointer fields, no embedded payload.
* Good, because adding a future target's scorecard is "create one file" with no shared-schema edits.
* Good, because each scorecard file is independently consumable by external tools (badge generators, dashboards).
* Bad, because the reproducibility envelope (codeograph_version, corpus_id, run_timestamp) repeats across the three files — mitigable by `run_id` correlation.

**(b) one unified `scorecard.json`.**
* Good, because single read for any consumer; cross-target comparison trivial.
* Good, because reproducibility envelope written once at the top.
* Bad, because it contradicts the plan §2 path layout — drift requires justification.
* Bad, because adding a target requires editing the unified file's `targets` object; collides with one-package extensibility.
* Bad, because schema evolution bumps a single shared version on any per-target change.

**(c) embedded in `manifest.json`.**
* Good, because single file for all run metadata; CI consumers parse one JSON.
* Bad, because `manifest.json` accretes responsibility — same god-bag pattern other ADRs explicitly avoid.
* Bad, because manifest must be re-written after eval (two-phase coupling).
* Bad, because external tools wanting only the manifest pay the scorecard cost.

**(d) separate files plus `scorecard-index.json`.**
* Good, because decouples scorecard navigation from manifest entirely.
* Bad, because adds a fourth file duplicating the manifest pointer's role.
* Bad, because two indexes (manifest + scorecard-index) confuse "which to consult".

### Fork 2 — Threshold model and check-result semantics

**(a) single boolean per check.**
* Good, because the simplest possible schema.
* Bad, because it contradicts the locked Fork 1 record shape that mandates `value` and `threshold`.
* Bad, because readers cannot see "92% (threshold ≥ 95%)" — only "fail".
* Bad, because it cannot accommodate judge scores at all.

**(b) tiered letter grades.**
* Good, because easy to scan in a table.
* Bad, because letter grades *are* the subjective buckets FR-12 forbids.
* Bad, because grade bands lack per-check justification.
* Bad, because forces boolean checks into a 5-bucket model.

**(c) discriminated-union with mechanical derivation. ✅ Chosen.**
* Good, because each check uses the threshold shape that fits its data.
* Good, because mechanically derived `result` eliminates an entire class of drift bug.
* Good, because `skip` semantics for the band gap answer the in-between case without inventing a fourth state.
* Good, because reserves the `ScoreBandThreshold` shape for v1.1 ADR-020 without committing to its implementation.
* Good, because Pydantic discriminated unions emit a clean JSON Schema for external consumers.
* Bad, because the discriminator adds one `kind` field per threshold — slightly more verbose JSON.

**(d) flat `dict[str, Any]` threshold.**
* Good, because maximally flexible.
* Bad, because no schema enforcement; typos silently produce wrong derivations.
* Bad, because external consumers can't write generic rendering code.
* Bad, because the discriminated union in (c) gets all the safety for marginal cost.

**(e) (c) plus per-check `display` field.**
* Good, because README renderer reads pre-formatted strings.
* Bad, because pre-formatted strings denormalize from `value` and `threshold` over time.
* Bad, because README rendering logic belongs in the README generator, not the scorecard schema.

### Fork 3 — Seven graph-quality checks

**(a) lock all seven exactly. ✅ Chosen.**
* Good, because FR-7a is a published seven-check contract; option (a) honors it.
* Good, because six deterministic checks are the right v1 floor — zero LLM cost.
* Good, because `semantic_accuracy` skip cleanly reserves the slot for ADR-020 (v1.1).
* Good, because every threshold cites a source ADR or FR row.
* Bad, because algorithm details (e.g., the five invariants of `internal_consistency`) lock into the ADR; additions are amendments.

**(b) names + thresholds only; defer algorithm details.**
* Good, because lighter ADR.
* Good, because algorithm refinements don't trigger amendments.
* Bad, because future contributors cannot read the ADR and know what `internal_consistency` actually checks.
* Bad, because citation rationale needs algorithm specificity to make sense.

**(c) (a) plus warn-only window on selected checks.**
* Good, because avoids "the very first eval blocks merge for a real-but-unanticipated case".
* Bad, because two-phase rollout adds a tightening date that must be tracked.
* Bad, because softer is the gateway drug to never tightening.
* Bad, because "warn-only" requires a new `enforced: bool` field — fights Fork 2's mechanical derivation.

**(d) drop `semantic_accuracy` from v1 entirely.**
* Good, because cleanest v1 — no skip records.
* Bad, because the seven checks named in FR-7a are the published contract; dropping one creates documentation drift.
* Bad, because a future reader cannot tell whether the check was forgotten or deferred.
* Bad, because re-introducing in v1.1 risks id collision with old scorecard files.

### Fork 4 — Three code-quality checks per target

**(a) lock all three slots exactly. ✅ Chosen.**
* Good, because honors FR-7 verbatim (three slots named `compile`, `coverage`, `llm_judge`).
* Good, because feature coverage answers "how much of my Spring app got translated?" — the question the side-by-side scorecard exists to answer.
* Good, because reuses ADR-010 Fork 9 audit data (refused / stub_todos) that would otherwise be log-only.
* Good, because v1.1 `test_coverage` extension is additive and clean.
* Bad, because the 95% / 85% band is judgment requiring calibration against the eval corpus.

**(b) coverage deferred to v1.1.**
* Good, because cleanest deferral — no novel feature-coverage definition introduced.
* Bad, because v1's code scorecard has two of three slots skipped — sells the v1 scorecard short.
* Bad, because wastes data already produced by ADR-010 Fork 9.
* Bad, because the reviewer's "how much translated?" question has no scorecard answer in v1.

**(c) coverage = render coverage.**
* Good, because trivially computable from per-class compile results.
* Bad, because render coverage duplicates information already in `compile`.
* Bad, because tautology under ADR-009's cap ("100% of the 3 classes we selected compiled").
* Bad, because hides the actual quality concern behind a compile-centric number.

**(d) four slots.**
* Good, because both meanings preserved with their own slots.
* Bad, because contradicts FR-7's "three checks per target" specification.
* Bad, because ADR-017 cannot rename FR-7 vocabulary without a plan amendment.

### Fork 5 — Eval invocation surface

**(a) subcommand only.**
* Good, because strict decoupling — eval works on any saved output dir.
* Good, because render iteration loop stays fast.
* Bad, because two steps for users who want one-command UX.

**(b) auto-run after `codeograph run`.**
* Good, because one command — best out-of-the-box UX.
* Good, because eval results always co-located with the producing run.
* Bad, because `reproducibility`'s 3× AST cost paid on every render unless user remembers `--no-eval`.
* Bad, because eval failure blocks render output preservation.
* Bad, because re-evaluating an old `out/` requires re-rendering.

**(c) separate `python -m evals` script.**
* Good, because cleanest separation — eval is scaffolding, not codeograph itself.
* Bad, because diverges from the established CLI extension pattern.
* Bad, because users remember a second invocation style.
* Bad, because distribution awkwardness — `evals/` must ship alongside the wheel.

**(d) subcommand + opt-in `--eval` sugar. ✅ Chosen.**
* Good, because default behaviour matches the cost model — reproducibility's 3× AST cost is paid only on explicit eval.
* Good, because eval is independently re-runnable on saved output for offline replay.
* Good, because one-command UX still available via opt-in.
* Good, because honors the established CLI extension pattern.
* Bad, because the two-ways-to-do-it surface is slightly larger — mitigated by `--eval` being literal sugar.

### Fork 6 — Compile-check execution policy

**(a) all sequential, fail-fast.**
* Good, because the simplest execution model.
* Good, because easy to debug — failing check's output is the last thing in the log.
* Bad, because slow — independent targets run back-to-back.
* Bad, because fail-fast within target hides the second failure.

**(b) parallel across, sequential within, continue.**
* Good, because parallel-across-targets wins on multi-target CI wall-clock.
* Good, because both checks' failures surface in one run.
* Good, because per-target log narrative stays coherent.
* Bad, because no cleanup means `node_modules/` accumulates across re-runs.

**(c) parallel everywhere.**
* Good, because maximum parallelism.
* Bad, because within-target ordering becomes non-deterministic.
* Bad, because two `npm`-using checks may race on `node_modules/`.
* Bad, because the performance win over (b) is marginal for typical 1-2-check renderers.

**(d) (b) plus cleanup + no-install policy. ✅ Chosen.**
* Good, because all of (b)'s parallelism + continue-on-failure benefits.
* Good, because explicit no-install — eval has zero network dependency and zero supply-chain surface.
* Good, because default no-cleanup makes scorecard failures locally reproducible.
* Good, because `--clean` opt-in handles the hot-loop disk-pressure case.
* Bad, because the future `CompileCheck.cleanup_paths` field is an ADR-008 amendment surface — kept as v1.1 deferred.

### Fork 7 — Multi-corpus support shape

**(a) single corpus per invocation; CI matrix; no aggregation.**
* Good, because trivial shape; eval logic stays single-corpus.
* Good, because CI matrix is the natural place for the corpus dimension.
* Bad, because no cross-corpus aggregation in v1 — README must hand-roll the side-by-side view.
* Bad, because drift risk over time as README author manually maintains the matrix.

**(b) suite config + multi-corpus invocation.**
* Good, because one command runs the whole matrix.
* Good, because combined summary is a first-class artefact.
* Bad, because diverges from Fork 5's single-output-dir shape.
* Bad, because suite config is a new artefact to maintain.
* Bad, because invocation becomes "all or nothing per suite".

**(c) single-corpus eval + `codeograph eval report`. ✅ Chosen.**
* Good, because honors Fork 5's locked subcommand shape.
* Good, because first-class aggregation surface mirroring `codeograph cache report` (ADR-015 pattern).
* Good, because markdown output makes README integration trivial.
* Good, because per-corpus invocation and aggregation are separable — CI can run one corpus in a fast loop and defer the report to merge.
* Bad, because two commands instead of one for the matrix case — documented with the canonical incantation.

**(d) (c) plus committed markdown + CI freshness gate.**
* Good, because README never goes stale relative to the latest eval.
* Good, because PR reviewer sees scorecard changes as a normal diff.
* Bad, because adds a CI gate and commits scorecard artefacts to repo history.
* Bad, because over-engineering for a v1 with two corpora; documented as v1.1 trigger at 4 corpora.

### Fork 8 — Manifest export of `compile_checks`

**(a) embed inline in `manifest.json`.**
* Good, because one file for all run metadata; eval reads manifest and has everything.
* Bad, because repeats Fork 1's rejected pattern of `manifest.json` accreting responsibility.
* Bad, because schema bump on `manifest.json` for every CompileCheck-shape change.
* Bad, because inconsistent with Fork 1 — scorecards are sidecar, compile-checks would be inline.

**(b) sidecar per target + manifest pointer. ✅ Chosen.**
* Good, because consistent with Fork 1's scorecard pattern — one mental model for per-target metadata.
* Good, because tamper-evident via the manifest sha256 (reuses established pattern).
* Good, because manifest stays minimal — additive pointer field, no embedded records.
* Good, because per-target file is independently consumable by external CI replay (the original ADR-008 deferral rationale).
* Good, because `CompileCheck` schema evolution bumps only the sidecar's `schema_version`.
* Bad, because one extra small file per target — minor directory-listing noise.

**(c) re-resolve at eval time.**
* Good, because no new field in any artefact; renderer is the live source of truth.
* Bad, because eval no longer decoupled — needs the codeograph package installed at eval time.
* Bad, because silent determinism gap — renderer version bumps change `compile_checks()` without changing the saved output.
* Bad, because breaks external CI replay use case.

**(d) (b) plus committed inside example dirs.**
* Good, because reproducibility envelope is committed alongside output; PR reviewers see compile-check changes as a normal diff.
* Neutral, because implicitly true given Fork 7's lock that `examples/*/out/` is committed — Option D is acknowledgement, not a new decision.

## More Information

### Relationships

* **ADR-001** (project skeleton) — `codeograph eval` is the new subcommand under the established Click CLI; pydantic-settings priority chain for any future eval-config fields.
* **ADR-006** (knowledge graph schema) — manifest schema bumps `1.2.0 → 1.4.0` (additive: `scorecards` field at 1.3.0, `compile_checks` field at 1.4.0); JSON Schema for the graph at `codeograph/schema/graph.schema.json` is the substrate for `schema_validity`.
* **ADR-007** (golden-graph pattern) — `golden_graph_agreement` reuses ADR-007's byte-equal comparison and multi-corpus support; `reproducibility` reuses ADR-007's reproducibility envelope.
* **ADR-008** (pluggable renderer interface) — `Renderer.compile_checks()` is the contract this ADR consumes; the manifest-export deferral on ADR-008 Fork 3 is resolved by Fork 8 of this ADR.
* **ADR-009** (rendering budget cap) — `SelectionResult.selected`, `skipped`, `bucket_membership`, `empty_buckets` are direct inputs to graph-quality checks and to `coverage`.
* **ADR-010** (Spring → TS/NestJS) — `SelectionResult.refused`, `stub_todos`, `feature_policies_active` plus the Spring feature coverage matrix are the substrate for the `coverage` slot.
* **ADR-013** (LLM provider abstraction) — eval can run entirely without invoking the provider in v1 (all LLM-mediated checks deferred); `--ast-only` mode (ADR-007) makes the `reproducibility` triple-run cheap.
* **ADR-014** (prompt versioning) — `prompt_id` and `prompt_content_hash` fields on `CheckResult` are populated by LLM-mediated checks (v1.1 only); v1 deterministic checks set them to `null`.
* **ADR-015** (telemetry + response cache) — eval reads aggregate cost/token data from telemetry rather than re-instrumenting; `codeograph cache report` is the precedent for `codeograph eval report`.

### Deferred items

* **`semantic_accuracy` (graph)** — slot reserved with `ScoreBandThreshold`; owned by the future LLM-judge calibration ADR (v1.1).
* **`llm_judge` (per-target code)** — slot reserved; owned by the same future ADR.
* **`test_coverage` (per-target code)** — additive new check id when rendered-test generation lands in the future snapshot + negative tests ADR (v1.1).
* **CI freshness gate for cross-corpus markdown report** — triggered when committed corpus count reaches 4 or when a manual freshness-drift incident occurs.
* **`CompileCheck.cleanup_paths` field** — additive ADR-008 amendment when the `--clean` flag needs to know per-renderer cleanup targets beyond `node_modules/`.
* **Tightening or loosening of `coverage` band** — based on corpus calibration data after the first eval cycle.
* **`--fail-fast` flag for compile-check execution** — added if a real use case emerges that justifies non-default fail-fast.
* **Third committed example corpus** — security-heavy edge-case corpus; v1.1 task once the two-corpus discipline proves out.

### Open Questions / Future Work

* Will the 95% / 85% feature-coverage band hold up against the two shipped corpora on the first eval run, or will the band need amendment before merge?
* Will `relationship_correctness` and `internal_consistency` sharp cutoffs cause day-one CI thrash on an edge case nobody anticipated, requiring an amendment?
* Will the cross-corpus markdown report shape integrate cleanly with the README, or will the table layout need a v1.1 redesign?
* Will the `compile_checks` sidecar pattern need extension to cover other per-target renderer-runtime metadata (e.g., a future "supported features list" per target)?
* Will external CI replay actually materialize as a use case, or will the eval surface remain internal-only — informing whether the sidecar pattern is over-engineered?
* Will `--clean` see real use in CI, or only in local hot-loop development?
* Will the `band_gap` skip semantics produce too much false-negative-feeling CI output, or will the soft signal prove valuable for "needs human review" gating?

### References

* Lanza, M., & Marinescu, R. (2006). *Object-Oriented Metrics in Practice.* Springer. — indirect via ADR-004 / ADR-009 threshold rationale propagated into `internal_consistency` and `coverage` derivations.
* JSON Schema specification — https://json-schema.org/ — for `scorecard.schema.json` and the auto-generation from Pydantic source.
* MADR template — https://github.com/adr/madr
