---
status: accepted
date: 2026-06-06
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-022 — Run Manifest and Structured Logging

## Context and Problem Statement

The manifest file (`<out>/manifest.json`) is the canonical run artefact — every other ADR consuming the output assumes a stable manifest shape. Three additive schema bumps have already shipped in v1 (`1.0` → `1.1` via DC2's `cache_stats`, → `1.3` via ADR-017 Fork 1's `scorecards`, → `1.4` via ADR-017 Fork 8's `compile_checks`) without an explicit codified rule. The next contributor adding a field has no normative guidance, and the rapid cadence creates risk that a structural change slips in.

Structured logging is similarly underspecified. FR-20 calls for `logs.jsonl` in a per-run directory; the implementation shipped a plaintext-only console pattern. ADR-015's telemetry JSONL handles per-LLM-call records; there is no parallel substrate for per-pipeline-event records (orchestrator INFO/WARN/ERROR lines, eval check execution traces, render progress, classifier decisions). Without one, eval framework lifecycle events, render progress, and the future LLM-judge invocations (v1.1 ADR-020) all reach stderr ad hoc and disappear when the terminal scrolls.

This ADR locks both substrates — manifest schema discipline and structured logging format — as the cross-cutting metadata layer every pipeline component honors. Decisions cover schema evolution rules (strict-additive within `1.x.x`), the manifest's three-category layout (scalar / aggregate / pointer), run-id generation, dual-emission logging format (JSONL file + plaintext stderr), per-run directory layout reconciling shipped reality with FR-20's literal text, log-level defaults and CLI flags, and manifest validation discipline including a committed JSON Schema for external consumers.

The framework introduces no new external service dependency. Manifest readers and writers use Pydantic as the source of truth with strict validation on write and lenient validation on read for forward compatibility. The committed JSON Schema (auto-generated from Pydantic and kept current via a CI freshness gate) is the external contract.

## Decision Drivers

* **Forward compatibility within v1** — strict-additive discipline means external consumers (and old codeograph installs reading new manifests) keep working across `1.x.x` versions.
* **No silent failures** — strict-on-write Pydantic validation catches typos at the boundary; CI freshness gate catches JSON-Schema drift; dual-emission logging keeps audit + human visibility in lockstep.
* **Determinism / determinism boundary clarity** — the run_id includes a random suffix and is in the "structural / not byte-stable" row of ADR-018's classification table; everything else stays byte-stable.
* **SOLID-clean composition** — the three-category manifest layout (scalar / aggregate / pointer) gives every future field a mechanical category-decision rule, preventing god-bag drift.
* **Industry-standard pattern** — `-v` / `-q` CLI shortcuts match universal convention; JSON Schema is the external-validation lingua franca; Python stdlib logging handlers are well-understood.
* **YAGNI** — per-component verbosity, log rotation, color output, env-var log overrides, `--runs-dir` flag, and field-deprecation cycles are all deferred to v1.1 with documented triggers.
* **Tractable v1 implementation** — seven forks produce a substrate that ships with one Pydantic source file, one JSON Schema regeneration step, one logging-config bootstrap, two handler classes, and a documented validation lifecycle.
* **Readability as a curated artefact** — the per-run directory layout is the user-visible thing reviewers inspect first; co-locating manifest + logs + telemetry + scorecards + rendered output under one `<out>` matches the principle of least surprise.

## Considered Options

### Fork 1 — Manifest schema evolution discipline

* **(a) strict additive within `1.x.x`; no remove/rename/type-change; `2.0.0` requires superseding ADR. ✅**
* (b) additive-default with documented two-version deprecation cycle.
* (c) additive plus rename-with-alias mechanism.
* (d) no codified rule; case-by-case per future ADR.

### Fork 2 — Manifest top-level layout policy

* **(a) three-category decision matrix: scalar / aggregate / pointer; aggregate ≤ 20 fields; pointer extras bounded to one boolean or one short string. ✅**
* (b) two-category with `meta` block grouping all scalars (requires breaking change).
* (c) all-pointer (requires breaking change).
* (d) author's discretion per field (no rule).

### Fork 3 — Run id generation

* (a) UUID v4 (random 128-bit; not sortable).
* (b) ISO 8601 timestamp with hyphens (sortable; same-second collision risk).
* **(c) timestamp + 6-hex random suffix (`YYYY-MM-DDTHH-MM-SSZ-<6 hex>`); sortable + collision-resistant + cross-OS safe + stdlib only. ✅**
* (d) content-hash based (confusing semantics).
* (e) ULID (sortable but encoded).

### Fork 4 — Structured logging format

* (a) JSONL only at console and file (machine-readable but dev-hostile).
* (b) plaintext only (human-readable but CI-hostile; violates FR-20).
* **(c) dual emission: JSONL to `<out>/logs.jsonl` + plaintext to stderr; single logging config with two handlers; eval-prefix convention preserved as `context.area` in JSONL and bracketed `[...]` in plaintext. ✅**
* (d) context-dependent (env-var branching; dual code paths).

### Fork 5 — Per-run directory layout

* **(a) formalize shipped co-located pattern: `<out>` IS the per-run directory; everything (manifest, logs, telemetry, evals, rendered output) lives under one tree; FR-20 reinterpreted; no `--runs-dir` flag in v1. ✅**
* (b) restructure to literal FR-20 (`runs/<run_id>/` for metadata; `<out>/` for artefacts) — violates Fork 1's strict-additive rule.
* (c) hybrid `<out>/runs/<run_id>/` namespace.
* (d) `--runs-dir` flag with current default.

### Fork 6 — Log levels and filtering CLI

* (a) five stdlib levels; `--log-level` primary flag only (no shortcuts).
* **(b) five stdlib levels; console INFO + file DEBUG (always-capture); `--log-level [DEBUG|INFO|WARNING|ERROR]` primary + `-v` / `-q` / `-qq` shortcuts mutually exclusive; same flags across all subcommands; summary table at INFO. ✅**
* (c) (a) plus per-component verbosity (`--log-component module=LEVEL`).
* (d) (b) plus `-q` suppresses end-of-run summary (violates ADR-009 Fork 4).

### Fork 7 — Manifest validation discipline

* **(a) strict at write time (Pydantic `extra="forbid"`); lenient at read time (`strict=False`); committed JSON Schema at `codeograph/_generated/manifest.schema.json` auto-generated from Pydantic; CI freshness gate mirrors ADR-014 prompt-freshness pattern. ✅**
* (b) strict on both write and read (breaks forward compatibility).
* (c) lenient on both write and read (silently accepts typos).
* (d) Pydantic-only with no committed JSON Schema (couples external consumers to package version).

## Decision Outcome

### Fork 1 — Schema evolution discipline: (a) strict additive within `1.x.x`

The locked rule:

> Within manifest `schema_version` `1.x.x`, every change MUST be:
>
> - **Add a new top-level field** with a default value or optional marker
> - **Add a new nested field inside an existing typed structure** with a default
> - **Bump PATCH** for clarifications (typos, documentation refinements without semantic change)
> - **Bump MINOR** for new fields (additive only)
>
> Operations explicitly FORBIDDEN within v1:
>
> - Remove a field
> - Rename a field
> - Change a field's type
> - Change a field's required/optional status (required → optional is forbidden because old consumers expect the field; optional → required is forbidden because old writers may emit without it)
> - Restructure nested objects
>
> Breaking changes require a `2.0.0` major-version bump AND a superseding ADR documenting the migration path. v1 ships `1.x.x` only.

The cadence already shipped follows this rule retroactively (every bump 1.0 → 1.4 has been additive). The rule formalizes the pattern so future contributors know it before authoring their next ADR.

**Companion artefact: `docs/manifest-versions.md`** — evolution log maintained alongside Pydantic source. One entry per version bump, naming the field added, the consuming ADR, and the bump-date. Lives in public docs; external consumers read it to learn what each version's fields mean.

### Fork 2 — Top-level layout: (a) three-category matrix

Every manifest field belongs to one of three categories:

| Category | Shape | Decision criterion | v1 locked examples |
|---|---|---|---|
| **Scalar metadata** | Single primitive value at top level: `field_name: value` | "Single value describing the run as a whole" | `schema_version`, `run_id`, `run_timestamp`, `source_path`, `codeograph_version`, `corpus_id` |
| **Aggregate metadata** | Small typed nested object: `field_name: {sub_key: ...}`; ≤ 20 sub-fields total; never grows linearly with corpus size | "Small structured rollup tightly coupled to this run; no independent external consumer" | `cache_stats: {pass1: {hits, misses, hit_rate}, pass2: {...}}` |
| **Payload pointer** | `field_name.<discriminator>: {path: str, sha256: str, ...one_optional_extra}`; the file lives at `path` relative to manifest | "File payload that grows linearly with corpus / target, OR is independently consumed by external tooling, OR needs tamper-evidence" | `artefacts.<name>`, `scorecards.<kind>`, `compile_checks.<target>` |

Canonical Pydantic class hierarchy (one base per category):

```python
# codeograph/manifest/schema.py
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ManifestAggregate(BaseModel):
    """Base for small typed rollup blocks. ≤ 20 nested fields total."""
    model_config = ConfigDict(extra="forbid")

class ManifestPointer(BaseModel):
    """Base for {path, sha256, +1 optional extra} pointer records."""
    model_config = ConfigDict(extra="forbid")
    path: str                                # PurePosixPath-shaped string, relative to manifest
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # subclasses MAY add ONE optional extra field (single bool or single short str)

class CacheStatsPass(ManifestAggregate):
    hits: int
    misses: int
    hit_rate: float

class CacheStats(ManifestAggregate):
    pass1: Optional[CacheStatsPass] = None
    pass2: Optional[CacheStatsPass] = None

class ArtefactPointer(ManifestPointer):
    pass                                     # no extras

class ScorecardPointer(ManifestPointer):
    overall: str = Field(pattern=r"^(pass|fail|skip|mixed)$")

class CompileChecksPointer(ManifestPointer):
    pass

class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # scalars
    schema_version: str
    run_id: str
    run_timestamp: str
    source_path: str
    codeograph_version: str
    corpus_id: str
    # aggregates
    cache_stats: Optional[CacheStats] = None
    # pointers
    artefacts: dict[str, ArtefactPointer] = Field(default_factory=dict)
    scorecards: Optional[dict[str, ScorecardPointer]] = None
    compile_checks: Optional[dict[str, CompileChecksPointer]] = None
```

**Cross-category transformation forbidden within v1** — a field originally added as aggregate cannot move to pointer (or vice versa); that would be remove-and-re-add, blocked by Fork 1.

**Naming convention** — scalars: `snake_case_noun`; aggregate blocks: `<concern>_stats`; pointer collections: `<concern>s` (plural noun).

### Fork 3 — Run id generation: (c) timestamp + 6-hex suffix

```python
# codeograph/manifest/run_id.py
import secrets
from datetime import datetime, timezone

def generate_run_id() -> str:
    """Format: YYYY-MM-DDTHH-MM-SSZ-<6 hex>
       Example: 2026-05-30T14-32-11Z-a3f2c8"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = secrets.token_hex(3)            # 24 random bits → 6 hex chars
    return f"{now}-{suffix}"

RUN_ID_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{6}$"
```

**Properties:**

| Property | How |
|---|---|
| Chronologically sortable | Timestamp prefix sorts alphabetically → chronologically |
| Collision-resistant | 24 random bits over a same-second window; effectively zero |
| Cross-OS filesystem-safe | Hyphens only; no `:` (Windows-forbidden), no `.`, no `_` |
| Human-readable | "I can see this run started 14:32 UTC today" |
| Stdlib only | `datetime` + `secrets`; no `ulid-py` or `uuid` extras |
| Cache-key stable | Generated once; never regenerated mid-run |

**Generation moment** — at pipeline start, in `codeograph run`'s orchestrator. Recorded on the first manifest write. Never regenerated.

**`codeograph eval`** reads the existing manifest's `run_id` to correlate eval-emitted scorecards with the original run. Does NOT generate a new run id.

**`assert_run_id_format` helper** added to `tests/helpers/determinism.py` (alongside the six locked in ADR-018 Fork 7); validates the regex above; called from any test asserting `run_id` shape.

### Fork 4 — Structured logging format: (c) dual emission

Single Python `logging.config.dictConfig` sets up two handlers attached to the same loggers:

```python
# codeograph/logging_config.py
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "jsonl": {
            "()": "codeograph.logging_formatters.JsonlFormatter",
        },
        "plaintext": {
            "()": "codeograph.logging_formatters.PlaintextFormatter",
            "fmt": "%(asctime)s %(levelname)-5s [%(area)s] %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
    },
    "filters": {
        "area_from_context": {
            "()": "codeograph.logging_filters.AreaFromContext",
            # Reads extra["context"]["area"] into record.area; falls back to logger name's last segment
        },
    },
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": "...",                # set dynamically to <out>/logs.jsonl
            "formatter": "jsonl",
            "level": "DEBUG",                 # always captures everything
            "encoding": "utf-8",
        },
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "plaintext",
            "level": "INFO",                  # default; CLI flag overrides
            "filters": ["area_from_context"],
        },
    },
    "loggers": {
        "codeograph": {
            "level": "DEBUG",                 # propagated to handlers; handlers filter further
            "handlers": ["file", "console"],
            "propagate": False,
        },
    },
}
```

Per-JSONL-record schema:

```python
{
    "ts": "2026-05-30T14:32:11.123Z",        # ISO 8601 UTC; ms precision
    "level": "INFO",                          # DEBUG | INFO | WARNING | ERROR | CRITICAL
    "run_id": "2026-05-30T14-32-11Z-a3f2c8",  # from LoggerAdapter
    "logger": "codeograph.evals.runner",      # source logger
    "context": {                              # extra fields the logger added
        "area": "eval/runner",
        "check_id": "structural_completeness",
        "check_value": 1.0
    },
    "msg": "structural_completeness: pass"
}
```

**`LoggerAdapter` for run_id propagation** — top-level components (orchestrator, eval runner, renderer) wrap their logger in a `LoggerAdapter` that injects `run_id` into every record's `extra` automatically.

**Eval-prefix convention preserved** — ADR-017 Fork 6's `[eval/<target>/<check_name>]` plaintext prefix emerges from `context.area`; the plaintext formatter reads `record.area` (populated by the `area_from_context` filter from `extra["context"]["area"]`) and substitutes it into the format string.

**Plaintext format** — `"%(asctime)s %(levelname)-5s [%(area)s] %(message)s"` — five-char left-aligned level; bracketed area; raw message.

**Console destination** — `sys.stderr`. `sys.stdout` reserved for primary CLI output (exit-code-bearing terse output).

**No rotation** in v1. One run produces one `logs.jsonl`. Disk pressure from a single run is bounded.

### Fork 5 — Per-run directory layout: (a) formalize shipped co-located pattern

The canonical layout matches what DC1–DC3 ship:

```
<out>/                                       ← passed via `--out`; one per run
├── manifest.json                            ← Fork 2 layout; Fork 7 validation
├── logs.jsonl                               ← Fork 4 dual-emission file output
├── graph.json                               ← Pass 0 artefact (ADR-006)
├── llm-annotations.json                     ← Pass 1+2 artefact (ADR-013)
├── telemetry/
│   └── run-<run_id>-*.jsonl                 ← per-LLM-call records (ADR-015)
├── <target>/                                ← e.g. "ts/"
│   ├── package.json
│   ├── tsconfig.json
│   ├── nest-cli.json
│   ├── .gitignore
│   ├── .env.example
│   └── src/
│       ├── main.ts
│       ├── app.module.ts
│       ├── config/...
│       ├── common/types/...
│       └── <feature>/...                    ← rendered classes per ADR-010
└── evals/
    ├── compile-checks.<target>.json         ← ADR-017 Fork 8
    ├── graph-scorecard.json                 ← ADR-017 Fork 1 (written by `codeograph eval`)
    ├── <target>-scorecard.json              ← ADR-017 Fork 1 (written by `codeograph eval`)
    └── <kind>-scorecard.compile.<name>.log  ← ADR-017 Fork 6 sidecar logs
```

**FR-20 reinterpretation** — ADR-022 explicitly documents:

> FR-20's literal `runs/<timestamp>/manifest.json` + `runs/<timestamp>/logs.jsonl` is reinterpreted as a conceptual run namespace. v1 implementation uses `<out>` as the per-run directory, with `run_id` recorded inside the manifest. The audit-trail intent of FR-20 is honored by the manifest's `run_id` field plus the co-located telemetry and log files.

**Per-run history via user discipline** — users wanting persistent multi-run history use distinct `--out` paths per run (e.g., `--out ./runs/$(date -u +%Y-%m-%dT%H-%M-%SZ)/`). The locked layout applies inside each path. No tool feature required.

**No `--runs-dir` flag in v1.** Deferred to v1.1 only if a real use case surfaces.

### Fork 6 — Log levels and CLI: (b) five stdlib levels + shortcuts

```python
import click

@click.group()
@click.option("--log-level",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"],
                                case_sensitive=False),
              default="INFO",
              help="Console log verbosity. File logs always at DEBUG.")
@click.option("-v", "verbose", count=True,
              help="Shortcut for --log-level DEBUG.")
@click.option("-q", "quiet", count=True,
              help="-q sets WARNING; -qq sets ERROR.")
def cli(log_level: str, verbose: int, quiet: int) -> None:
    if verbose and quiet:
        raise click.UsageError("-v and -q are mutually exclusive.")
    if verbose:
        log_level = "DEBUG"
    elif quiet == 1:
        log_level = "WARNING"
    elif quiet >= 2:
        log_level = "ERROR"
    configure_logging(console_level=log_level)
```

**Five stdlib levels**: `DEBUG=10`, `INFO=20`, `WARNING=30` (`WARN` accepted as alias), `ERROR=40`, `CRITICAL=50`. `CRITICAL` not exposed via CLI (too restrictive for any real use; would suppress every operational signal).

**Defaults:**
- Console handler: `INFO`
- File handler: `DEBUG` (captures everything regardless of console filter; the audit trail is for offline analysis)

**Cross-CLI consistency:** the same flag set applies to every codeograph subcommand (`run`, `eval`, `eval report`, `cache stats`, `cache purge`, `cache report`). All commands share the logging-config bootstrap.

**Summary table at INFO** — ADR-009 Fork 4's end-of-run summary is `logger.info(...)`; suppressed only at `--log-level WARNING` or above (= `-qq` or `-q` shortcut equivalent). Documented as expected behavior; users scripting `codeograph` to avoid all output use `-qq`.

**No per-component verbosity** in v1. Deferred to v1.1 with documented trigger (a real debugging case where component-level control would have saved time).

**No env-var override.** `LOG_LEVEL=DEBUG` not supported. Rationale: minimize ways-to-do-same-thing in v1.

**No color output** in v1. Plain ANSI-free formatter. `NO_COLOR` env var moot. v1.1 may add `rich` if a real need surfaces.

### Fork 7 — Manifest validation discipline: (a) strict write, lenient read, committed JSON Schema, CI freshness gate

**Write path** — every manifest write goes through Pydantic with `extra="forbid"`:

```python
# codeograph/manifest/io.py
from pathlib import Path
from .schema import Manifest

def write(manifest: Manifest, path: Path) -> None:
    """Strict-on-write: Pydantic's extra='forbid' rejects unknown fields;
       all required fields validated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

def read(path: Path) -> Manifest:
    """Lenient-on-read: forward-compatible across `1.x.x` versions.
       Unknown fields (from newer codeograph versions) dropped with DEBUG log."""
    import json, logging
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Manifest.model_validate(raw, strict=False)
```

**Two-phase write integrity:**
- Initial write (at run start, after Pass 0): scalars populated; `artefacts.{graph, llm-annotations}` pointers populated; optional fields (`cache_stats`, `scorecards`, `compile_checks`) absent or empty. Passes full strict validation.
- Post-update writes (after Pass 1+2, after eval): read existing manifest with lenient read; modify in-place; re-write with strict serialization. Passes full strict validation after every phase.

**No "partial manifest" schema** — same schema works for both phases because optional fields default cleanly to `None` or empty container.

**JSON Schema generation:**

```python
# codeograph/manifest/schema_cli.py
import json
from pathlib import Path
import click
from .schema import Manifest

GENERATED_SCHEMA_PATH = Path("codeograph/_generated/manifest.schema.json")

def regenerate() -> dict:
    return Manifest.model_json_schema()

@click.command()
@click.option("--generate", is_flag=True, help="Write the JSON Schema to disk.")
@click.option("--check", is_flag=True,
              help="Exit non-zero if committed schema doesn't match Pydantic source.")
def main(generate: bool, check: bool) -> None:
    current = regenerate()
    if check:
        committed = json.loads(GENERATED_SCHEMA_PATH.read_text())
        if committed != current:
            raise click.ClickException(
                "manifest.schema.json is stale; regenerate with --generate"
            )
    elif generate:
        GENERATED_SCHEMA_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
```

**CI freshness gate** — added to the `lint` job (ADR-018 Fork 6):

```yaml
- name: Verify manifest JSON Schema is current
  shell: bash
  run: python -m codeograph.manifest.schema_cli --check
```

Mirrors ADR-014's prompt-freshness gate exactly. Same pattern for `codeograph/evals/scorecard.schema.json` (ADR-017 Fork 1) — both checks run in the lint job.

**External consumer guarantee** — any standard JSON Schema validator (`ajv`, `python-jsonschema`, `jsonschema-cli`, etc.) can validate a manifest against `codeograph/_generated/manifest.schema.json`. Forward-compatible reads succeed; strict validators flag unknown fields as warnings.

### Constraint flagged for ADR-018 (test strategy)

`assert_run_id_format` helper is added to `tests/helpers/determinism.py` (Fork 3 of this ADR), bringing the helper count from six (ADR-018 Fork 7) to seven. ADR-018's classification table is amended: `run_id` field becomes a "structural / regex-validated" row referencing `assert_run_id_format`.

### Constraint flagged for ADR-023 (secret scanning)

The committed JSON Schema (`codeograph/_generated/manifest.schema.json`) and the manifest itself contain no secrets — manifest scalars include `source_path` (filesystem path; could theoretically contain a username) but no API keys, tokens, or credentials. Gitleaks scanning the repo and the per-run `<out>/manifest.json` (if a user commits an output dir) should not trigger on locked manifest fields. ADR-023's allowlist policy must accommodate the `source_path` field's filesystem-path content.

### Constraint flagged for future ADR-024 (output-path safety, v1.1)

The shipped pattern of overwriting `<out>` on re-run (Fork 5) is the user-facing surface ADR-024 will add `--force` discipline to. ADR-024 doesn't change Fork 5's layout; it adds a pre-write check that `<out>` is empty or `--force` is set.

## Consequences

**Positive.**
1. Manifest schema evolution becomes mechanical for future contributors — three-category matrix plus strict-additive rule plus canonical Pydantic class hierarchy means adding a new field is a single decision (which category?) plus a single edit (the appropriate base class).
2. External consumers can validate manifests independently of installed codeograph version via the committed JSON Schema.
3. The CI freshness gate prevents the JSON Schema from drifting from the Pydantic source — same operational discipline that proved out for ADR-014's prompt-freshness gate.
4. Dual-emission logging gives both human-readable console output (for local dev) and machine-parseable JSONL (for CI parsing and offline replay) without env-var branching.
5. The `run_id` format is filesystem-safe across OSes (no `:`), chronologically sortable in `ls`, collision-resistant under parallel matrix runs, and stdlib-generable without a new dependency.
6. The per-run directory layout matches user expectation from the `--out` flag — one self-contained tree per run.
7. The five-level CLI with `-v` / `-q` / `-qq` shortcuts matches universal CLI convention; users coming from `git`, `pytest`, `mvn` feel at home.
8. Forward compatibility within `1.x.x` means old codeograph installs reading manifests from newer codeograph runs succeed; the lenient-read path silently drops unknown fields.

**Negative.**
1. Strict-additive within v1 means a badly-designed field lives forever; cleanup waits for v2.0 with a superseding ADR. Friction is intentional but real.
2. The three-category matrix is one more concept future contributors must internalize before adding a manifest field. Documented in `docs/manifest-versions.md`.
3. The asymmetric strict-write / lenient-read Pydantic invocation requires two different code paths in the manifest IO module — documented but is real complexity.
4. Dual logging emission means two formatters to maintain; format changes require updating both.
5. The CI freshness gate adds a workflow step (mirrors ADR-014 / ADR-017 schema gates); contributors forgetting to run the regeneration before pushing hit the gate.
6. FR-20's literal text is reinterpreted, not honored — a careful reader comparing the plan against the implementation sees the divergence. ADR-022's text documents the rationale.
7. The summary table is INFO-suppressed only at `WARNING`+ — a user running `-qq` for "no output" mode loses visibility into the cap-binding behavior; documented as expected.
8. No env-var log level override means CI workflows can't set `LOG_LEVEL=DEBUG` once — every invocation must pass `-v` or `--log-level DEBUG`.

## Confirmation

1. The `Manifest` Pydantic class has `model_config = ConfigDict(extra="forbid")`; calling `Manifest.model_validate({**valid_data, "rogue_field": "x"})` raises `ValidationError` (verified by unit test).
2. Calling `Manifest.model_validate({**valid_data, "rogue_field": "x"}, strict=False)` succeeds and emits a DEBUG log record naming the dropped field (verified by unit test asserting both behaviors).
3. Running `python -m codeograph.manifest.schema_cli --check` on a clean repo exits 0; modifying `Manifest` source without regenerating `codeograph/_generated/manifest.schema.json` causes the same command to exit non-zero (verified by integration test).
4. `generate_run_id()` produces a string matching the regex `^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{6}$` (verified by parametrized unit test).
5. Two calls to `generate_run_id()` in rapid succession produce different strings (collision check; verified by unit test that calls 1000 times and asserts uniqueness).
6. Running `codeograph run ./fixture --out ./out` produces `./out/manifest.json` containing all six locked scalar fields plus an `artefacts.graph` pointer with valid sha256 hex (verified by integration test).
7. The same run produces `./out/logs.jsonl` containing at least one record per pipeline phase (Pass 0, Pass 1, Pass 2), each record matching the JSONL schema (verified by integration test loading the JSONL).
8. Running with `--log-level DEBUG` produces console output containing at least one record at the DEBUG level; running with default `--log-level INFO` produces console output containing no DEBUG records (verified by CLI integration test using `caplog`).
9. Running with `-v` is equivalent to `--log-level DEBUG`; running with `-qq` is equivalent to `--log-level ERROR`; running with both `-v` and `-q` exits non-zero with a Click `UsageError` (verified by three CLI tests).
10. `codeograph eval ./out` reads the manifest's `run_id` and writes scorecards whose schema includes that same `run_id`; running eval does NOT change the manifest's `run_id` (verified by integration test).
11. The committed `codeograph/_generated/manifest.schema.json` validates against the JSON Schema 2020-12 meta-schema and declares `$schema: "https://json-schema.org/draft/2020-12/schema"` (verified by lint).
12. A manifest written by a hypothetical future codeograph version (`schema_version: 1.5.0` with an additional `eval_stats: {...}` field) is read successfully by the current codeograph; the unknown `eval_stats` field is dropped with a DEBUG log; the strict-additive contract holds across versions (verified by a fixture-based forward-compat test).

## Pros and Cons of the Considered Options

### Fork 1 — Schema evolution discipline

**(a) strict additive + v2.0 major escape hatch. ✅ Chosen.**
* Good, because it matches the precedent of three already-shipped additive bumps.
* Good, because external-consumer stability is the load-bearing property.
* Good, because the v2.0 escape hatch provides genuine relief for badly-designed fields.
* Good, because Pydantic + JSON Schema express the rule cleanly.
* Bad, because a badly-designed field lives forever in v1 timeframe.

**(b) additive-default with two-version deprecation cycle.**
* Good, because it permits cleaning up bad-design fields without a v2.0 bump.
* Good, because the deprecation cycle is documented and predictable.
* Bad, because it adds operational discipline (tracking sweeps before removal) that v1's single internal consumer doesn't need.
* Bad, because it's infrastructure for a use case that doesn't materialize in v1.

**(c) additive plus rename-with-alias.**
* Good, because it allows fixing awkward field names without breaking external consumers.
* Bad, because duplicate fields confuse readers and external JSON Schema consumers.
* Bad, because alias mechanism is Pydantic-specific.

**(d) no codified rule.**
* Good, because maximally flexible.
* Bad, because identical to the current state we're explicitly trying to formalize.
* Bad, because different contributors reach different conclusions over time.

### Fork 2 — Top-level layout policy

**(a) three-category decision matrix. ✅ Chosen.**
* Good, because three categories cover every existing field without retrofit.
* Good, because decision criteria are testable (size-bounded, linear-growth-bounded).
* Good, because the 20-field cap on aggregate and pointer-extras cap prevent god-bag drift.
* Good, because each category has a canonical Pydantic shape contributors copy-paste.
* Bad, because three categories require contributors to internalize the criteria.

**(b) two categories with `meta` block.**
* Good, because simpler than three.
* Bad, because it forces restructure of currently-top-level scalars — breaking change forbidden by Fork 1.
* Bad, because scalars and aggregates have different shapes; grouping them muddles the rule.

**(c) all-pointer.**
* Bad, because it forces restructure of every existing field — breaking change forbidden by Fork 1.
* Bad, because trivial scalars become tiny sidecar files.

**(d) author's discretion.**
* Good, because maximum flexibility.
* Bad, because identical to the pre-fork state; produces inconsistency over time.

### Fork 3 — Run id generation

**(a) UUID v4.**
* Good, because no collision risk.
* Bad, because not sortable chronologically.
* Bad, because no readable signal in directory name.
* Bad, because 36-char length clutters log lines.

**(b) ISO 8601 timestamp with hyphens.**
* Good, because sortable and human-readable.
* Bad, because same-second collision is a real CI parallel-matrix failure mode.

**(c) timestamp + 6-hex random suffix. ✅ Chosen.**
* Good, because combines sortability and collision resistance.
* Good, because visible human-readable timestamp.
* Good, because cross-OS filesystem-safe.
* Good, because stdlib only.
* Good, because honors FR-20 ("`<timestamp>` directory name" interpreted as "timestamp-derived run id").
* Good, because length (26 chars) is right for log ergonomics.
* Bad, because introduces non-determinism (mitigated by ADR-018 Fork 7 classification).

**(d) content-hash based.**
* Good, because short.
* Bad, because not sortable chronologically.
* Bad, because "hash" semantics suggest reproducibility but inputs include timestamp.

**(e) ULID.**
* Good, because sortable and collision-resistant by design.
* Bad, because less human-readable than (c).
* Bad, because new dependency.

### Fork 4 — Structured logging format

**(a) JSONL only at console and file.**
* Good, because one format end-to-end; CI parsing trivial.
* Good, because honors FR-20 literally.
* Bad, because console output is unreadable for humans; local inner-loop becomes jq ceremony.
* Bad, because ADR-017 Fork 6's eval-prefix convention requires reshape.

**(b) plaintext only.**
* Good, because human-readable everywhere.
* Good, because preserves eval-prefix convention.
* Bad, because CI parsing is brittle.
* Bad, because violates FR-20.
* Bad, because run_id only in filename, not per record.

**(c) dual emission: JSONL file + plaintext stderr. ✅ Chosen.**
* Good, because honors FR-20 (JSONL file).
* Good, because preserves human-readable console.
* Good, because preserves eval-prefix convention as context.area.
* Good, because console grep-friendly for local dev; file jq-friendly for CI.
* Good, because single logging config; two handlers.
* Bad, because two formatters to maintain.

**(d) context-dependent (env-var branching).**
* Good, because each environment gets its preferred format.
* Bad, because two code paths complicate testing.
* Bad, because env-var conditional behavior is implicit; surprises readers.
* Bad, because local dev loses on-disk JSONL audit trail (FR-20 violation locally).

### Fork 5 — Per-run directory layout

**(a) formalize shipped co-located pattern. ✅ Chosen.**
* Good, because honors Fork 1's strict-additive rule — no existing path moves.
* Good, because matches user expectation from `--out` (self-contained directory).
* Good, because `codeograph eval <output-dir>` works without changes.
* Good, because renderer output sits naturally alongside metadata.
* Bad, because diverges from FR-20's literal path text — requires explicit reinterpretation documentation.

**(b) literal FR-20 restructure (`runs/<run_id>/` separate).**
* Good, because honors FR-20 literally.
* Bad, because violates Fork 1's strict-additive rule.
* Bad, because eval becomes two-directory aware.
* Bad, because splits audit trail.

**(c) hybrid `<out>/runs/<run_id>/` namespace.**
* Good, because honors FR-20 namespace.
* Bad, because manifest no longer at `<output-dir>/manifest.json` — breaks ADR-017 Fork 5.
* Bad, because adds nesting depth without justification.

**(d) `--runs-dir` flag with current default.**
* Good, because maximally flexible.
* Bad, because breaks consistency between manifest pointer paths and scorecard paths if dirs split.
* Bad, because adds CLI surface for an unrequested use case.

### Fork 6 — Log levels and CLI

**(a) five levels + `--log-level` only (no shortcuts).**
* Good, because minimal CLI surface.
* Bad, because lacks universal `-v` / `-q` shortcuts.

**(b) (a) + `-v` / `-q` / `-qq` shortcuts mutually exclusive. ✅ Chosen.**
* Good, because matches universal CLI convention (`git`, `mvn`, `pytest`).
* Good, because file captures everything regardless of console verbosity.
* Good, because no per-component complexity in v1.
* Good, because preserves ADR-009 Fork 4 summary-table visibility.
* Bad, because three flag styles to test.

**(c) (a) + per-component verbosity.**
* Good, because maximum control.
* Bad, because substantial CLI surface unjustified by real v1 demand.

**(d) (b) + `-q` suppresses summary table.**
* Good, because truly quiet mode for scripted invocations.
* Bad, because violates ADR-009 Fork 4 contract — summary is the primary user-facing visibility mechanism.

### Fork 7 — Manifest validation discipline

**(a) strict write + lenient read + committed JSON Schema + CI freshness gate. ✅ Chosen.**
* Good, because strict-on-write catches contributor typos at the boundary.
* Good, because lenient-on-read preserves forward compatibility within `1.x.x`.
* Good, because single Pydantic source plus committed derived JSON Schema.
* Good, because CI freshness gate prevents drift (mirrors ADR-014 pattern).
* Good, because external tooling validates independently.
* Good, because two-phase write works without partial-schema complexity.
* Bad, because asymmetric write/read mode requires two Pydantic invocations.

**(b) strict on both write and read.**
* Good, because maximum safety.
* Bad, because breaks forward compatibility on every minor bump.
* Bad, because external tooling pinned to a specific codeograph version.

**(c) lenient on both.**
* Good, because forward compatible by accident.
* Bad, because typos and forgotten fields silently succeed.
* Bad, because loses the value of Pydantic.

**(d) Pydantic-only with no committed JSON Schema.**
* Good, because single source of truth.
* Bad, because external consumers must import codeograph package to validate.
* Bad, because contradicts ADR-017 Fork 1 precedent.

## More Information

### Relationships

* **ADR-001** (project skeleton) — Click CLI; pydantic-settings; AI-permitted boilerplate covers CI YAML and logging config.
* **ADR-006** (knowledge graph schema) — base manifest shape; canonical-form sha256 substrate; this ADR codifies the additive-only discipline that ADR-006 implicitly assumed.
* **ADR-008** (pluggable renderer) — `dict[PurePosixPath, bytes]` return shape; the renderer's path keys land relative to `<out>` per Fork 5.
* **ADR-009** (rendering budget cap) — end-of-run summary table is INFO-level output; Fork 6 preserves visibility.
* **ADR-013** (LLM provider abstraction) — `LlmProvider` middleware emits log records via `codeograph.llm.*` loggers; honors this ADR's level configuration.
* **ADR-014** (prompt versioning) — prompt-freshness CI gate is the precedent for Fork 7's manifest JSON Schema freshness gate.
* **ADR-015** (telemetry + response cache) — telemetry JSONL records per-LLM-call at `<out>/telemetry/run-*.jsonl`; structured logging from Fork 4 emits at `<out>/logs.jsonl`; both files co-exist and cross-reference via `run_id`.
* **ADR-017** (eval framework) — committed `scorecard.schema.json` is the precedent for Fork 7's `manifest.schema.json`; ADR-017 Fork 1's scorecard pointer pattern + Fork 6's eval-prefix convention both honored here.
* **ADR-018** (test strategy) — `assert_run_id_format` helper added to `tests/helpers/determinism.py` per Fork 3; classification table updated.

### Deferred items

* **Field deprecation cycle** (Option B of Fork 1) — deferred to v1.1 if a real bad-design field surfaces requiring cleanup before v2.0.
* **Per-component log verbosity** (`--log-component module=LEVEL`) — deferred to v1.1 if a real debugging case demands it.
* **`--runs-dir` flag** for separate metadata directory — deferred to v1.1 if a multi-run-history use case surfaces.
* **Log rotation** for very long runs — deferred to v1.1; v1 worst-case bounded.
* **Color output via `rich`** — deferred to v1.1; v1 ships plain ANSI-free.
* **`LOG_LEVEL` env-var override** — deferred to v1.1 with documented trigger (a real CI use case where flag-per-invocation is friction).
* **Backporting fixes to older manifest minor versions** — not supported; v1 ships one "latest" schema at any time.
* **Manifest pretty-print toggle** — deferred to v1.1; v1 always pretty-prints (`indent=2`).

### Open Questions / Future Work

* Will the three-category matrix prove too coarse — will future contributors need a fourth category for a real use case? Watch for "doesn't fit cleanly" amendments in subsequent ADRs.
* Will the 20-field cap on aggregate metadata hold, or will `cache_stats` grow past it requiring a sub-cap subdivision?
* Will the lenient-read forward-compat path actually exercise in v1 (would require an external consumer or an old codeograph install reading a new manifest) — or remain theoretical until v1.1?
* Will the `run_id` 6-hex suffix prove collision-free in real parallel-matrix CI runs, or will a collision motivate widening to 8 hex in v2.0?
* Will the dual-emission JSONL + plaintext stay narrow enough to maintain, or will format additions in v1.1 (color, rich, OpenTelemetry export) demand a formatter rewrite?
* Will FR-20's literal text reinterpretation create friction with future contributors reading the plan, or will the ADR-022 cross-reference suffice?

### References

* Pydantic v2 documentation — https://docs.pydantic.dev/
* JSON Schema 2020-12 specification — https://json-schema.org/draft/2020-12/schema
* Python `logging` module — https://docs.python.org/3/library/logging.html
* MADR template — https://github.com/adr/madr
