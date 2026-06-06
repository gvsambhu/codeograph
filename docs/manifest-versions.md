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
| 1.7.0 | 2026-06-06 | `run_id` scalar (Optional) | ADR-017 Fork 3 + ADR-015 | Eval-correlation `run_id` carrying UUID4 values at ship time. **Format change to timestamp+hex coming in DC5 M7** (value-level only, no schema bump per ADR-022 Fork 1). |

## DC5 (current development)

DC5 introduces a new manifest package at `codeograph/codeograph/manifest/`
with the same field set as `1.7.0`. The `Manifest` Pydantic class replaces
the auto-generated `codeograph/graph/models/manifest_schema.py`; the
`CacheStats` shape is preserved verbatim per ADR-022 Fork 1's strict-additive
rule. The `run_id` format change (UUID4 → `YYYY-MM-DDTHH-MM-SSZ-<6 hex>`) is
value-level only, so no `schema_version` bump is required.

**Locked target:** `1.7.0` at DC5 ship. The Pydantic source of truth lives
at `codeograph/codeograph/manifest/schema.py`; the committed JSON Schema
artefact is regenerated from it.

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
