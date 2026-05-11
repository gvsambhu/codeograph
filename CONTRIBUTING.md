# Contributing

## Commits

**Conventional Commits.** Subject line: `<type>(<scope>): <summary>`.

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.
Scopes follow the codebase layout: `parser`, `graph`, `input`, `analyzer`, `cli`, `schema`, `ci`, `adr`, `golden`.

Every commit ends with a co-author trailer:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

Use the bare `Claude` form — never pin a model version, it dates the history.

## Branching

- `main` — protected. Only merged via PR.
- `dev/feature-<N>` — long-lived feature branch for a delivery chunk.
- `dev/<topic>` — short-lived topic branches that merge into a `dev/feature-*` branch (e.g. `dev/dc1-bugs`).

Direct pushes to `main` are not used. Every change goes through a PR.

## Pre-merge checklist

All of these must be green before a PR merges:

```bash
make lint                                      # ruff check + format check
make typecheck                                 # mypy strict
pytest -m "not integration" --tb=short         # Python unit tests
pytest -m "tier1"                              # golden tests (skips if no JVM)
cd codeograph/parser/java && mvn test          # Java parser tests
```

CI enforces these on every push to `dev/**` and on PRs to `main`. See `.github/workflows/ci.yml`.

## Golden tests

The Tier 1 golden test (`tests/test_golden.py`) compares the emitted `graph.json` against checked-in goldens under `tests/goldens/tier1/`. When a deliberate change affects graph output:

1. Run `make golden-update` to regenerate goldens.
2. Diff the result. Make sure every change in the diff is intended.
3. Commit the regenerated goldens together with the code change in the same PR.

JavaParser version bumps (in `pyproject.toml` `[tool.codeograph.versions]`) always require a goldens refresh.

## Banned terms

The following must not appear anywhere in source, tests, docs, ADRs, or commit messages:

```
sakila        peerislands       interview
assignment    peer islands      submission
engineering director
```

Enforced by NFR-1 and reviewed before merge.

## ADRs

Architecture decisions land as ADRs under `docs/adr/`, numbered sequentially. Amendments to an existing ADR go in the same file under an "Amendment" heading with the date and rationale. Don't backfill ADRs to justify code — write the ADR first, then implement.
