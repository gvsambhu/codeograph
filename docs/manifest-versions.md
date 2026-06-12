# Manifest Version Evolution Log

This document records every schema version bump for the run manifest at
`<out>/manifest.json`. Per [ADR-022](adr/ADR-022-run-manifest-and-structured-logging.md)
Fork 1, the manifest evolves **strict-additively** within `1.x.x` —
no field removal, rename, type change, or required/optional flip.
Breaking changes require a `2.0.0` major bump + superseding ADR.

The JSON Schema at `codeograph/_generated/manifest.schema.json` is the
external contract for manifest consumers; it is regenerated from the
Pydantic source of truth (`codeograph/codeograph/manifest/schema.py`)
via `python -m codeograph.manifest.schema_cli --generate` and pinned by
a CI freshness gate.

## Bump history

| Version | Date | Field added | Consuming ADR | Notes |
|---|---|---|---|---|
| 1.0.0 | 2026-05-09 | (initial) | ADR-006 | DC1 baseline: scalar metadata + `artefacts.graph` / `artefacts.llm_annotations` pointers. |
| 1.1.0 | 2026-05-23 | `cache_stats` (aggregate) | ADR-005 + ADR-013 | DC2 added per-pass LLM cache rollup keyed by pass name. |
| 1.3.0 | 2026-05-30 | `scorecards` pointer collection | ADR-017 Fork 1 | R8a introduced eval scorecards; `1.2` was skipped (no published 1.2 release). |
| 1.4.0 | 2026-05-30 | `compile_checks` pointer collection | ADR-017 Fork 8 | Compile-check sidecar per renderer target. |
| 1.5.0 | 2026-06-06 | `source_path` scalar | ADR-017 Fork 3 | Eval reproducibility check re-runs `--ast-only` against the same source. |
| 1.6.0 | 2026-06-06 | `corpus_id` scalar | ADR-017 Fork 3 | `golden_graph_agreement` check locates `tests/goldens/<corpus_id>/graph.json`. |
| 1.7.0 | 2026-06-06 | `run_id` scalar (Optional) | ADR-017 Fork 3 + ADR-015 | Eval-correlation `run_id` carrying UUID4 values at ship time. |
| **2.0.0** | 2026-06-07 | (restructure — **major bump**) | **ADR-025** | **Breaking.** Flat layout: `scorecards`/`compile_checks` promoted to top-level (peers of `artefacts`); per-artefact `schema_version` retained; `sha256` **required** + top-level `llm_skipped` flag (omit `llm_annotations` on `--ast-only`); `run_id` now **required**; `cache_stats` cost fields (`saved/incurred_usd_est`) dropped — re-add additively when a cost model lands; `run_id` format = `YYYY-MM-DDTHH-MM-SSZ-<6 hex>`. Supersedes ADR-022 manifest forks (1/2/7) + ADR-015 Fork 6 `cache_stats` shape. Strict-additive resumes within `2.x`. |

## DC5 (shipped 2026-06-12)

DC5 introduces a new manifest package at `codeograph/codeograph/manifest/`
and ships the manifest at **`2.0.0`** per [ADR-025](adr/ADR-025-manifest-schema-flat-layout.md)
— a deliberate restructure (flat layout) of the shipped `1.7.0` nested shape.
The `Manifest` Pydantic class (hand-written, source of truth) replaces the
auto-generated `codeograph/graph/models/manifest_schema.py`, which is deleted.

`2.0.0` changes vs `1.7.0`: `scorecards`/`compile_checks` move to the top level;
`sha256` becomes required (with a top-level `llm_skipped` flag + omission of the
`llm_annotations` pointer on `--ast-only`); `run_id` becomes required and adopts
the `YYYY-MM-DDTHH-MM-SSZ-<6 hex>` format; per-artefact `schema_version` is
retained; `cache_stats` carries `{calls, hits, hit_rate}` only (cost fields
deferred until a cost model exists). Strict-additive evolution resumes within
`2.x.x`.

**Locked target:** `2.0.0` at DC5 ship. The Pydantic source of truth lives at
`codeograph/codeograph/manifest/schema.py`; the committed JSON Schema artefact
at `codeograph/_generated/manifest.schema.json` is regenerated from it.

## Future bumps (v1.1+)

Any future additive change follows the table format above: one row per
`schema_version` bump, naming the field, the consuming ADR, and the
bump date. Per ADR-022 Fork 7, every bump requires:

1. Update `codeograph/codeograph/manifest/schema.py`.
2. Run `python -m codeograph.manifest.schema_cli --generate`.
3. Commit the regenerated `codeograph/_generated/manifest.schema.json`
   alongside the source change.
4. CI freshness gate (`python -m codeograph.manifest.schema_cli --check`)
   catches drift on subsequent PRs.

## References

- [ADR-022 — Run Manifest and Structured Logging](adr/ADR-022-run-manifest-and-structured-logging.md)
  (the load-bearing design ADR; Forks 1 + 2 + 7 govern this log)
- [ADR-006 — Knowledge Graph Schema](adr/ADR-006-knowledge-graph-schema.md)
  (the base manifest shape; canonical-form sha256 substrate)
- [ADR-017 — Eval Framework](adr/ADR-017-eval-framework.md)
  (consuming ADR for the `scorecards` + `compile_checks` pointer collections and the `source_path` / `corpus_id` / `run_id` scalars)
