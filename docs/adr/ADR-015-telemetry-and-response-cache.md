---
status: accepted
date: 2026-05-17
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-015 — Telemetry and Response Cache

## Context and Problem Statement

Codeograph's LLM pipeline issues hundreds of calls per corpus across Pass 1 (annotate), Pass 2 (synthesize), and Pass 3 (render). Each call costs money, takes time, and produces output worth caching. The legacy implementation had **no telemetry** (calls were logged via stdlib `logger.info` at best) and a **domain-keyed cache** that silently served stale results after prompt or model changes — a domain whose `pass1_dir/<domain>.json` cache file existed got the cached output regardless of whether the prompt that produced it still existed. The combination meant cost was unmeasured and correctness was unverifiable.

ADR-015 fixes both. Telemetry records every LLM call as a structured JSONL row carrying provider, model, tier, purpose, prompt version + content hash, token usage, latency, retry timeline, cache-hit flag, and cost estimate. The response cache is a content-addressed SQLite store with a key composed of `(model, prompt_id, prompt_version, prompt_content_hash, rendered_input_hash, schema_hash, max_tokens)` — every component that would change the response is in the key, and nothing that wouldn't. Both surfaces are wired in via the middleware pattern from ADR-013 Fork 3; the provider itself is unaware of them.

The scope is narrow: this ADR defines the telemetry record schema, the cache storage backend, the cache key composition, the invalidation policy, and the hit-reporting surface. The middleware wrappers themselves (`CachingLlmProvider`, `TelemetryLlmProvider`) are declared in ADR-013; ADR-015 specifies what they read and write.

## Decision Drivers

* **Fix the legacy domain-keyed cache bug.** Cache key must change whenever any input that affects the response changes; never silently serve stale results.
* **Fix the legacy "stdout-only logging" gap.** Every LLM call produces a structured, machine-readable record with cost, tokens, and outcome.
* **Code-only delivery model.** Telemetry and cache artefacts ship with the run output; no external service required for a v1 deliverable to be inspectable.
* **Reproducibility for eval (ADR-007).** Telemetry record carries enough identifiers to reproduce any past call exactly.
* **Cost reporting.** Per-run summary on stdout; per-pass breakdown in `manifest.json`; cross-run aggregation via `codeograph cache report`.
* **Disk-space management.** Cache grows over time; user must have visible control without surprise eviction.
* **No external service for inspection.** v1 telemetry artefacts must be self-contained — no API keys, no cloud service, no offline-breakage. A user with the run's output directory has everything needed to inspect what happened.
* **Composable with ADR-013 middleware pattern.** Telemetry and caching live as wrappers over the bare `LlmProvider`; no provider class changes.
* **Schema evolution path.** Telemetry record format and cache schema both have visible versioning; future format changes don't silently corrupt historical data.

## Considered Options

Each fork below was evaluated against the drivers. Options that were considered and rejected appear in the Pros and Cons section at the end.

### Fork 1 — Telemetry backend

* **(a) Structured JSONL files in `<output_dir>/telemetry/`. ✅**
* (b) Python `logging` with structured handler (`structlog` / `python-json-logger`).
* (c) OpenTelemetry exporter (OTLP).
* (d) Cloud telemetry service (Langfuse / Helicone).
* (e) Hybrid — JSONL default, OTel exporter opt-in.

### Fork 2 — Telemetry record schema

* **(a) Single event per call with nested `attempts[]` array. ✅** (event granularity)
* **(b) Denormalized `pipeline_name` + `pipeline_run_id` in every record. ✅** (span hierarchy)
* **(c) Explicit `schema_version` field. ✅** (versioning)
* **(d) Hash-only — `input_hash` + `output_hash`; bodies stored only in cache. ✅** (privacy)

### Fork 3 — Cache storage backend

* (a) Filesystem (one file per cache entry, content-addressed path).
* **(b) SQLite single file `<cache_dir>/cache.db`. ✅**
* (c) In-memory only.
* (d) Pluggable backend ABC + filesystem default.
* (e) Tiered (in-memory L1 + on-disk L2).

### Fork 4 — Cache key composition

* **7 components — `model`, `prompt_id`, `prompt_version`, `prompt_content_hash`, `rendered_input_hash`, `schema_hash`, `max_tokens`; null-byte separator; sha256[:16]. ✅**

### Fork 5 — Cache invalidation policy

* (a) Never expire (manual purge only).
* (b) Size-bounded LRU eviction.
* (c) TTL-based eviction.
* **(d) Manual purge + advisory size warning; rich `codeograph cache` CLI. ✅**
* (e) TTL + manual pin.

### Fork 6 — Cache hit reporting

* (a) Stdout summary only.
* (b) Stdout + manifest cache_stats.
* **(c) Stdout + manifest cache_stats + `codeograph cache report` cross-run CLI. ✅**
* (d) HTML dashboard.

## Decision Outcome

### Fork 1 — Telemetry backend: (a) Structured JSONL

Telemetry records land in `<output_dir>/telemetry/run-<corpus_id>-<timestamp>.jsonl`. One file per run; one record per LLM call.

```python
# codeograph/telemetry/emitter.py
class TelemetryEmitter(ABC):
    @abstractmethod
    def emit(self, record: TelemetryRecord) -> None: ...
    @abstractmethod
    def close(self) -> None: ...

class JsonlEmitter(TelemetryEmitter):
    def __init__(self, path: Path):
        self._fh = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def emit(self, record: TelemetryRecord) -> None:
        line = json.dumps(record.to_dict(), separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            self._fh.close()
```

Zero deps. Stdlib `json` + `pathlib` + `threading`. Inspectable with `jq`, `pandas`, `duckdb -c "select * from 'telemetry/*.jsonl'"`. Ships with run artefacts; entire run is reproducible from the directory.

Future expansion (e.g., OTel exporter) lands as an additional `TelemetryEmitter` impl — additive change.

### Fork 2 — Telemetry record schema

Combined decision across the four sub-forks:

```json
{
  "schema_version": "1.0",
  "ts": "2026-05-16T10:42:13.847Z",
  "trace_id": "C-7b2a8e3d-4c2a-…",
  "pipeline_name": "pass_1",
  "pipeline_run_id": "PR-2026-05-16-abc123",
  "corpus_id": "petclinic-abc123",

  "provider": "anthropic",
  "model": "claude-sonnet-4-5",
  "override_model": null,
  "tier": "FAST",
  "purpose": "ANNOTATE",

  "prompt_id": "annotate_node",
  "prompt_version": "v3",
  "prompt_content_hash": "7b2a8e3d",

  "input_hash": "f3a8b1c290a4...",
  "output_hash": "92e1d5f7a3b6...",

  "input_tokens": 4321,
  "output_tokens": 156,
  "cached_tokens": 3892,
  "input_estimated": 4318,

  "cache_hit": false,
  "status": "success",
  "error_class": null,
  "error_message": null,

  "total_latency_ms": 30847,
  "attempts": [
    {"attempt": 1, "latency_ms": 30000, "status": "error",   "error_class": "LlmTransientError"},
    {"attempt": 2, "latency_ms":   847, "status": "success", "error_class": null}
  ],

  "cost_usd_est": 0.0142
}
```

```python
# codeograph/telemetry/record.py
@dataclass(frozen=True)
class TelemetryRecord:
    schema_version: str = "1.0"
    ts: str                              # ISO 8601 UTC
    trace_id: str
    pipeline_name: str                   # pass_1 | pass_2 | pass_3
    pipeline_run_id: str
    corpus_id: str
    provider: str
    model: str
    override_model: str | None
    tier: str                            # FAST | DEEP | RENDER
    purpose: str                         # ANNOTATE | SYNTHESIZE | RENDER
    prompt_id: str
    prompt_version: str
    prompt_content_hash: str
    input_hash: str
    output_hash: str | None              # null on terminal failure
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    input_estimated: int | None
    cache_hit: bool
    status: str                          # success | error
    error_class: str | None
    error_message: str | None            # short summary, NOT stack trace
    total_latency_ms: int
    attempts: list[Attempt]
    cost_usd_est: float
```

**Sub-fork 2a — Event granularity: single event per call with nested `attempts[]`.** One row per call simplifies aggregation; nested `attempts` preserves per-attempt detail for debugging slow / retried calls.

**Sub-fork 2b — Span hierarchy: denormalized.** `pipeline_name` and `pipeline_run_id` are fields on every record. No separate `pipeline_start` / `pipeline_end` events. Pipeline-level totals computed via `group by pipeline_run_id`.

**Sub-fork 2c — Schema versioning: explicit `schema_version`.** Required field. Bumped on breaking changes (renames, semantic shifts). Tools branch on version for backward compatibility.

**Sub-fork 2d — Privacy: hash-only.** `input_hash` and `output_hash` only; full bodies live in the cache (Fork 3), not in telemetry. Looking up a specific call's body is "find the row by `trace_id`, take `input_hash`, query `cache.db`."

### Fork 3 — Cache storage backend: (b) SQLite

```sql
PRAGMA user_version = 1;

CREATE TABLE cache_entries (
  cache_key TEXT PRIMARY KEY,         -- 16-char hex from Fork 4
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  tier TEXT NOT NULL,                 -- metadata, not in key
  purpose TEXT NOT NULL,              -- metadata, not in key
  prompt_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  prompt_content_hash TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  schema_hash TEXT NOT NULL,
  max_tokens INTEGER NOT NULL,
  input_body TEXT NOT NULL,           -- for telemetry input_hash lookup
  output_body TEXT NOT NULL,          -- the cached response (JSON)
  token_usage_json TEXT NOT NULL,     -- serialized TokenUsage
  created_at TIMESTAMP NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0,
  last_hit_at TIMESTAMP
);

CREATE INDEX idx_prompt ON cache_entries(prompt_id, prompt_version);
CREATE INDEX idx_model  ON cache_entries(model);
CREATE INDEX idx_created ON cache_entries(created_at);
```

```python
# codeograph/llm/cache/sqlite_backend.py
class SQLiteCacheBackend(CacheBackend):
    def __init__(self, path: Path):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._migrate()

    def get(self, key: str) -> CacheEntry | None: ...
    def put(self, key: str, entry: CacheEntry) -> None: ...
    def stats(self) -> CacheStats: ...
    def purge(self, *, older_than_days: int | None = None,
              prompt_version: str | None = None,
              model: str | None = None) -> int: ...
```

Single file `<cache_dir>/cache.db`. Stdlib `sqlite3` — zero deps. WAL mode for concurrent reads + serialized writes. `PRAGMA user_version` for schema migration; bumped when schema changes. Hit-count tracking is one column update per access. Per-prompt-version invalidation is one SQL `DELETE`.

Atomic guarantees (ACID) eliminate the temp-file-and-rename ceremony filesystem caches require.

### Fork 4 — Cache key composition: 7 components, null-byte separator, sha256[:16]

```python
# codeograph/llm/cache/key.py
import hashlib
import json
from pydantic import BaseModel

def compute_cache_key(
    *,
    model: str,
    prompt_id: str,
    prompt_version: str,
    prompt_content_hash: str,
    rendered_input: str,
    schema: type[BaseModel],
    max_tokens: int,
) -> str:
    """Return a deterministic 16-hex-char cache key.

    The key composition includes every field that affects the response,
    and nothing that doesn't. See ADR-015 Fork 4 for the full rationale.
    """
    components = [
        model,
        prompt_id,
        prompt_version,
        prompt_content_hash,
        hashlib.sha256(rendered_input.encode("utf-8")).hexdigest(),
        hashlib.sha256(
            json.dumps(schema.model_json_schema(), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        str(max_tokens),
    ]
    joined = "\0".join(components)     # null byte — cannot appear in any component
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
```

**Components in the key (response-affecting):**

| Component | Source | Why in key |
|---|---|---|
| `model` | ADR-013 Fork 1 (resolved from tier or override) | Different model = different response |
| `prompt_id` | ADR-014 Fork 1 | Different prompt = different response |
| `prompt_version` | ADR-014 Fork 2 | Different version = different content |
| `prompt_content_hash` | ADR-014 Fork 2 | Silent-edit defense |
| `rendered_input_hash` | this ADR | Different input = different response |
| `schema_hash` | this ADR | Different output schema = different tool-use call |
| `max_tokens` | this ADR | Affects truncation |

**Components NOT in the key (response-irrelevant):**

| Component | Why excluded |
|---|---|
| `tier` | Resolves to `model` via config; including would over-key |
| `purpose` | Same input → same output regardless of caller intent; **metadata column** for analytics |
| `cache_hint` | Billing concern, not response content |
| `pipeline_run_id`, `corpus_id`, `trace_id` | Run-specific; including would defeat cross-run reuse |
| `temperature` | **Locked at 0 for v1 structured-output.** Documented assumption; future ADR amendment adds it AND bumps `PRAGMA user_version` |

**Hashing choices:**

* **Separator `\0` (null byte)** — cannot appear in valid model names, prompt IDs, hex hashes, or JSON. Eliminates concatenation ambiguity.
* **Truncation to 16 hex chars (64 bits)** — birthday-collision probability negligible at our scale (~50% at 4 billion entries; we operate at thousands).
* **sha256** — standard, fast, no security weakness for this non-security context.
* **`schema.model_json_schema()` with `sort_keys=True`** — Pydantic v2 ships this; sorting ensures stable hashes across schema rebuilds.

### Fork 5 — Cache invalidation: (d) Manual purge + advisory warning

No automatic eviction. Cache grows until the user acts. CLI surfaces size on every run; advisory warning above threshold:

```
$ codeograph annotate ./corpus
Pass 1 complete: 247 calls (89 cache hits, 36%) — ~$2.14 saved, ~$3.72 incurred.
[cache] 1.2 GB across 8,421 entries — consider 'codeograph cache purge --older-than 90d'
```

CLI commands:

```
codeograph cache stats                                    # report size, entries, breakdown
codeograph cache purge                                    # dry-run by default
codeograph cache purge --all
codeograph cache purge --older-than 90d
codeograph cache purge --prompt-version v2
codeograph cache purge --model claude-sonnet-4-5
```

Advisory thresholds in `pyproject.toml`:

```toml
[tool.codeograph.cache]
warn_size_mb = 1024
warn_entry_count = 50000
```

The user stays in control. Eval reproducibility (ADR-007) is never broken by surprise — old entries remain accessible as long as the user hasn't purged them.

### Fork 6 — Cache hit reporting: (c) Stdout + manifest + cross-run CLI

**Per-run stdout summary** (one line per pass at completion):

```
Pass 1 complete: 247 calls (89 cache hits, 36%) — ~$2.14 saved, ~$3.72 incurred.
Pass 2 complete:   8 calls ( 0 cache hits,  0%) — first run on this corpus.
Pass 3 complete:  47 calls (47 cache hits, 100%) — fully cached.
```

**Manifest field** (`manifest_version` bumps 1.0 → 1.1):

```json
{
  "manifest_version": "1.1",
  "corpus_id": "petclinic-abc123",
  "artifacts": { ... },
  "cache_stats": {
    "pass_1": { "calls": 247, "hits": 89, "hit_rate": 0.36,
                "saved_usd_est": 2.14, "incurred_usd_est": 3.72 },
    "pass_2": { "calls": 8,   "hits": 0,  "hit_rate": 0.0,
                "saved_usd_est": 0.0,  "incurred_usd_est": 1.83 },
    "pass_3": { "calls": 47,  "hits": 47, "hit_rate": 1.0,
                "saved_usd_est": 0.94, "incurred_usd_est": 0.0 }
  }
}
```

**Cross-run CLI** (`codeograph cache report --since 30d`):

```
Cache performance over last 30 days:
  Total runs: 47
  Total calls: 14,231
  Cache hits: 6,847 (48.1%)
  Cost saved: ~$142.36
  Cost incurred: ~$203.78

Hit rate trend (weekly):
  Week of 2026-04-18: 32%
  Week of 2026-04-25: 39%
  Week of 2026-05-02: 44%
  Week of 2026-05-09: 51%

Top 5 most-hit prompts:
  annotate_node v3 — 3,421 hits
  render_file v2 — 1,847 hits
  ...

Top 5 most-missed prompts (cache prefix optimization candidates):
  synthesize_corpus v1 — 894 misses
  ...
```

All inputs are `telemetry/*.jsonl` files; the CLI is `glob + parse + group_by + format`. No new storage; no separate aggregation store.

## Consequences

**Positive.**

* Cache key is content-addressed across every response-affecting input; silent-staleness (the legacy bug) is structurally impossible.
* Telemetry is per-call, structured, machine-readable, ships with every run as an artefact.
* SQLite cache is a single file — easy to share, snapshot, back up, version.
* WAL mode + serialized writes give safe concurrent reads with no extra ceremony.
* Per-prompt-version invalidation is one SQL statement; full purge flexibility via `codeograph cache purge` flags.
* Hit-count and last-hit-at tracked natively in SQLite; cross-run analytics via `codeograph cache report`.
* No external service required for telemetry; no API keys, no offline-breakage; eval reproducibility automatic.
* Manifest carries per-run cache stats; CI gates can assert on them.
* JSONL records can be re-aggregated into any future telemetry sink (Langfuse, OTel) via a post-processing script without re-instrumentation.
* `cost_usd_est` reconciliation possible later via a price-table update without touching call sites.
* `schema_version` and `PRAGMA user_version` give visible evolution paths for both telemetry and cache formats.

**Negative.**

* SQLite cache file is binary; `cat cache.db` is unreadable. Mitigated by `sqlite3 cache.db ".dump cache_entries"` or `codeograph cache stats`.
* No automatic disk-space management — user-controlled, but requires user awareness; mitigated by the advisory warning.
* `cache report` CLI re-scans telemetry JSONL files on every invocation; slow at 10k+ runs. Acceptable for v1 scale; would optimize with a derived rollup table if it becomes painful.
* `cost_usd_est` requires a price-table per model; price-table is hard-coded for v1; price changes by providers require code update.
* Telemetry record carries 30+ fields; JSON line lengths grow. At 500-1000 bytes per line, a 500-call Pass 1 = ~500 KB; manageable but not free.
* SQLite single-writer constraint means multi-process concurrent runs of `codeograph annotate` on the same corpus contend; not a v1 use case but documented as a limitation.
* Hash-only privacy means debugging a "wrong output" requires cache hit (or rerun); telemetry alone can't tell you what the prompt said.
* `PRAGMA user_version` requires migration code per schema change; small ongoing maintenance.

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. **`TelemetryEmitter` ABC and `JsonlEmitter` impl** at `codeograph/telemetry/emitter.py`; one file per run; flush on every emit; thread-safe.
2. **`TelemetryRecord` dataclass** at `codeograph/telemetry/record.py` with all 30+ fields from Fork 2's schema, including `schema_version`, `attempts[]`, `pipeline_name`, hash-only privacy.
3. **`SQLiteCacheBackend`** at `codeograph/llm/cache/sqlite_backend.py`; `PRAGMA journal_mode=WAL`; `PRAGMA user_version` for migration; all CRUD operations + `stats` + `purge` flag combinations.
4. **`compute_cache_key(...)`** at `codeograph/llm/cache/key.py`; pure function; null-byte separator; sha256[:16]; exhaustive unit test covering "same components = same key", "any component diff = different key".
5. **`CachingLlmProvider` and `TelemetryLlmProvider`** middleware wrappers (from ADR-013 Fork 3) integrated with SQLite cache and JSONL emitter respectively.
6. **`codeograph cache` CLI command group** at `codeograph/cli/cache.py` with `stats`, `purge` (dry-run default), and `report` subcommands.
7. **Manifest gets `cache_stats` block** — `manifest_version` bumped to `1.1`; per-pass stats populated by the orchestrator.
8. **Advisory warning** triggers when `cache.db` size exceeds `tool.codeograph.cache.warn_size_mb` or entry count exceeds `warn_entry_count`.
9. **Per-run stdout summary** prints one line per pass at completion (calls / hits / hit-rate / saved / incurred).
10. **Schema documentation** — `docs/telemetry-schema.md` describes the JSONL record fields; `docs/cache-schema.md` describes the SQLite tables and key composition; both are updated when `schema_version` / `user_version` is bumped.

## Pros and Cons of the Considered Options

### Fork 1 — Telemetry backend

**(a) Structured JSONL. ✅ Chosen.**
* Good, because zero deps; stdlib only.
* Good, because inspectable with `jq`, `pandas`, `duckdb`.
* Good, because ships with run artefacts; reproducibility envelope is self-contained.
* Good, because no external service required for inspection; works offline; CI without secrets.
* Good, because CI-friendly — tests assert on JSONL contents directly.
* Bad, because no live UI; reading the file is the only way to see what happened.
* Bad, because no built-in cross-run aggregation (mitigated by Fork 6's `cache report` CLI).

**(b) Python `logging` with structured handler.**
* Good, because familiar; plays with existing log infrastructure.
* Bad, because telemetry mixed with regular log lines is fragile.
* Bad, because logging is loss-tolerant; telemetry should be guaranteed.

**(c) OpenTelemetry exporter.**
* Good, because industry-standard semantic conventions; first-class span hierarchy.
* Good, because exporter swap (Jaeger, Tempo, Datadog, Honeycomb) without re-instrumentation.
* Bad, because heavy deps (~10 MB); significant setup overhead — initialise tracer provider, configure exporters, manage shutdown.
* Bad, because reading the output requires OTel-aware tooling for full benefit; JSONL exporter loses the tree-structure advantage.
* Bad, because conceptual overhead (spans, resources, exporters, propagators) is heavyweight for a CLI-grade tool.

**(d) Cloud telemetry service.**
* Good, because best UI for exploring runs, comparing prompts, tracking cost.
* Bad, because external dep; offline / CI breakage without API keys.
* Bad, because cost (free tiers limited; per-event charges in production usage).
* Bad, because vendor lock-in; migrating to a different backend means re-instrumenting.

**(e) JSONL + opt-in OTel extras.**
* Good, because default works; power users get OTel.
* Bad, because opt-in tooling is rarely used in practice; YAGNI.
* Bad, because two code paths to test.

### Fork 2 — Telemetry record schema

**(2a) Single event per call with nested `attempts[]`. ✅ Chosen.**
* Good, because one row per call simplifies aggregation.
* Good, because nested `attempts` preserves per-attempt debugging detail.
* Good, because cache lookup is just a boolean field.
* Bad, because querying nested arrays needs `unnest()` (acceptable).

**(2b) Denormalized pipeline fields. ✅ Chosen.**
* Good, because single event type; aggregation via simple `group by`.
* Bad, because no exact pipeline-span timing (use `max(ts) - min(ts)`; acceptable approximation).

**(2c) Explicit `schema_version`. ✅ Chosen.**
* Good, because breaking changes versionable; historical records parseable.
* Good, because matches project pattern (manifest_version, content_hash_pin, PRAGMA user_version).
* Bad, because one more field; discipline required.

**(2d) Hash-only privacy. ✅ Chosen.**
* Good, because no leakage surface.
* Good, because debugging routed to cache (one store, one purpose).
* Bad, because debugging requires cache hit or rerun.

### Fork 3 — Cache storage backend

**(a) Filesystem (one file per entry).**
* Good, because trivially inspectable.
* Good, because zero deps.
* Bad, because per-file overhead on Windows NTFS; many small files at scale.
* Bad, because hit-count tracking requires separate index file.

**(b) SQLite single file. ✅ Chosen.**
* Good, because single-file artefact aligns with E1's code-only delivery.
* Good, because hit-count tracking native (column update).
* Good, because per-prompt-version invalidation is one `DELETE`.
* Good, because scales to 100k+ entries without breath.
* Good, because stdlib; zero deps.
* Good, because ACID; interrupted writes never leave half-entries.
* Good, because `PRAGMA user_version` for schema migration.
* Bad, because binary file (mitigated by `sqlite3 ".dump"`).
* Bad, because single-writer (acceptable for single-process CLI).

**(c) In-memory only.**
* Good, because fastest.
* Bad, because defeats the cache's primary purpose (cross-run reuse).

**(d) Pluggable backend ABC + filesystem default.**
* Good, because future-proof.
* Bad, because premature abstraction for v1.

**(e) Tiered L1/L2.**
* Good, because hot-path speed.
* Bad, because complexity for unclear v1 benefit; LLM call latency dominates.

### Fork 4 — Cache key composition

**7 components, null-byte separator, sha256[:16]. ✅ Chosen.**
* Good, because every component has a concrete "would the response change?" justification.
* Good, because every excluded component is deliberately so.
* Good, because null-byte separator eliminates concatenation ambiguity.
* Good, because 16 hex chars are collision-free at our scale.
* Good, because `temperature` exclusion is honest (locked at 0 for v1) and migration-friendly (future change bumps `PRAGMA user_version`).
* Bad, because adds one pure function to test; ~30 LOC of exhaustively-tested code.

### Fork 5 — Cache invalidation

**(a) Never expire.**
* Good, because maximum hit rate; no surprises.
* Bad, because unbounded disk growth.

**(b) Size-bounded LRU.**
* Good, because disk usage bounded.
* Bad, because evicts rarely-touched eval entries silently; reproducibility breaks.

**(c) TTL-based.**
* Good, because predictable expiry.
* Bad, because TTL is a guess; reproducibility breaks at TTL boundary.

**(d) Manual purge + advisory warning. ✅ Chosen.**
* Good, because user stays in control; eval reproducibility never broken by surprise.
* Good, because rich CLI flags (`--older-than`, `--prompt-version`, `--model`, `--all`) cover the real use cases.
* Good, because honest about uncertainty — TTLs and size caps are guesses dressed up as policy.
* Good, because fits "single-user CLI" deployment model.
* Bad, because requires user action when size matters; warning may be ignored.

**(e) TTL + manual pin.**
* Good, because bounded growth + reproducibility via pin.
* Bad, because pin mechanism is new surface area; "why cache miss?" troubleshooting gets harder.

### Fork 6 — Cache hit reporting

**(a) Stdout only.**
* Good, because immediate feedback.
* Bad, because ephemeral; no machine-readable record.

**(b) Stdout + manifest.**
* Good, because per-run cache impact reproducible.
* Bad, because no cross-run aggregation.

**(c) Stdout + manifest + `cache report` CLI. ✅ Chosen.**
* Good, because each layer serves a distinct audience.
* Good, because cross-run aggregation without external dashboard tooling.
* Good, because "most missed prompts" surface is actionable.
* Good, because inputs are existing JSONL files; no new storage.
* Bad, because re-scans JSONL on every invocation (acceptable at v1 scale).

**(d) HTML dashboard.**
* Good, because best exploration UX.
* Bad, because significant implementation cost (HTML templating, charting library, asset bundling — easily 500+ LOC + a dep).
* Bad, because duplicates capabilities of dedicated observability platforms; scope creep into "we built our own mini-dashboard."

## More Information

**Relationships to other ADRs.**

* **ADR-005 §6** — prompt-cache pass-through is the upstream commitment that makes per-call billing reduction meaningful. Telemetry's `cached_tokens` field captures the savings.
* **ADR-007** — eval framework golden tests reproduce past calls; telemetry record's `(prompt_id, prompt_version, prompt_content_hash, input_hash, model)` give the exact identifiers needed.
* **ADR-013** — ADR-013 declares `CachingLlmProvider` and `TelemetryLlmProvider` as wrapper classes; ADR-015 specifies what they read and write (cache schema, telemetry record shape).
* **ADR-014** — `prompt_version` and `prompt_content_hash` flow from ADR-014's `Prompt` object through ADR-013's `CallContext` into this ADR's cache key and telemetry record.
* **ADR-016** (cost-control CLI flags, v1.1) — `cost_usd_est` from telemetry feeds the `--max-cost-usd` budget check; cache hit-rate informs `--prefer-cache` flag.
* **ADR-017** (eval framework, v1.1) — eval pipelines consume telemetry JSONL directly for prompt-quality regression analysis.

**Deferred items.**

* **Cost-price table externalization** — for v1, the per-model price table is a constant in code. Future amendment moves it to `pyproject.toml` or a separate JSON file for easier updates when providers change pricing.
* **`cache report` rollup table** — if `cache report` becomes slow due to JSONL volume (>10k runs), add an opt-in derived SQLite rollup that aggregates telemetry into a separate `<cache_dir>/report.db`.
* **HTML report generation** — if exploration UX becomes valuable, generate a static HTML report from JSONL. Probably not needed; dedicated LLM-observability platforms (Langfuse, Helicone) serve the rich-UI use case better when external tooling is acceptable.
* **OpenTelemetry exporter** — if a user needs to ship telemetry to Jaeger / Honeycomb / Datadog, add a `TelemetryEmitter` impl that translates `TelemetryRecord` to OTel spans. v1.1 or later.
* **Distributed cache backend** (Redis, S3) — if multi-process or multi-machine runs become a use case, extract `CacheBackend` ABC and add new impls. v1.x or later.

**Open questions for future review.**

The following questions should be revisited once concrete telemetry and cache usage has accumulated:
1. Did the cache key composition stay correct, or did a response-affecting field get missed?
2. Did the JSONL telemetry scale cleanly, or did the `cache report` CLI become slow?
3. Did the SQLite cache stay performant, or did we hit migration / WAL / file-size pain?
4. Did users actually use `codeograph cache purge`, or did `cache.db` grow without anyone noticing?
5. Did the advisory warning prove sufficient, or did we need to add automated eviction after all?
6. Did `cost_usd_est` match the actual invoice within ±5%, or did the price table drift?
7. Did `manifest.cache_stats` get used in CI gates, or did it sit unread?

**References.**

* MADR template — https://github.com/adr/madr
* JSON Lines specification — https://jsonlines.org/
* SQLite WAL mode — https://www.sqlite.org/wal.html
* SQLite `PRAGMA user_version` — https://www.sqlite.org/pragma.html#pragma_user_version
* DuckDB JSONL queries — https://duckdb.org/docs/data/json/overview.html
* Anthropic prompt caching — https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
* OpenTelemetry GenAI semantic conventions (future reference) — https://opentelemetry.io/docs/specs/semconv/gen-ai/

## Amendments

**2026-06-07 — `cache_stats` manifest shape now owned by ADR-025.** Fork 6 placed a per-pass
`cache_stats` block in the manifest with fields `{calls, hits, hit_rate, saved_usd_est,
incurred_usd_est}`. The manifest shape is restructured to `2.0.0` by **ADR-025 (Manifest Schema 2.0.0)**,
which now owns the `cache_stats` shape. Under ADR-025 the v1 block is `{calls, hits, hit_rate}` only:
the cost-estimate fields (`saved_usd_est`, `incurred_usd_est`) are **out of v1 scope** because v1 has no
cost model, and are re-added as an additive `2.x` manifest bump **when a cost model is introduced** (the
future cost-control work, or an amendment to this ADR that lands the per-model price table). No reversal
of the telemetry / cache-backend / cache-key decisions of this ADR; the change is to the manifest
`cache_stats` field set only.
