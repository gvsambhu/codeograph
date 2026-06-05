## Summary
- Eval framework: scorecard schema, 7 graph checks, 3 code checks, runner, cross-corpus report, `codeograph eval` + `eval report` CLI
- Test infrastructure: ADR-018 marker taxonomy (`slow`/`external`/`eval`), mock LLM provider + builder, 6 determinism helpers, mini-corpora, 80% coverage gate
- Manifest schema 1.7.0 (additive: `source_path`, `corpus_id`, `run_id`)
- Compile-checks sidecar (renderer-side metadata for eval framework)
- Two example corpora (`spring-rest-sample`, `spring-blog-api`) with committed `out/`
- 5-job CI: `lint` → `unit` → `integration-external` → `eval` (matrix) → `report`
- CONTRIBUTING.md + .gitattributes

## ADRs implemented
- ADR-017 (eval framework) — all 8 forks
- ADR-018 (pytest test strategy) — all 7 forks
- ADR-006 amendment — manifest schema 1.6.0 → 1.7.0

## Fixup rounds
- DC4-FIXUP-01 — 13 issues (10 original + 3 post-merge lint), all landed

## Test plan
- [ ] CI all 5 jobs green
- [ ] Coverage ≥ 80% on `codeograph/`
- [ ] No banned terms in diff or commit messages