# Contributing

## Commits

**Conventional Commits.** Subject line: `<type>(<scope>): <summary>`.

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.
Scopes follow the codebase layout: `parser`, `graph`, `input`, `analyzer`, `cli`, `schema`, `ci`, `adr`, `golden`.

Every AI-assisted commit ends with two attribution trailers:

```
Co-authored-by: <AI brand> <noreply@<provider>>
AI-Model: <api-model-identifier-with-release-date>
```

Concrete forms by tool:

```
# Claude Code (Opus / Sonnet)
Co-authored-by: Claude <noreply@anthropic.com>
AI-Model: claude-opus-4-1-20250805

# Google Antigravity (Gemini)
Co-authored-by: Gemini <noreply@google.com>
AI-Model: gemini-2.5-pro-20251201
```

Rules:

- Use the **bare brand** in `Co-authored-by:` — never pin a model version inline, it dates the history.
- Put the model identifier (with release date when available) on the separate `AI-Model:` line — preserves audit traceability if a model release has a known regression.
- Mixed-tool commits (rare) include both trailer pairs.
- Hand-written commits (no AI assistance) include neither trailer.

## Branching

- `main` — protected. Only merged via PR.
- **Design work:** `design/r<N>-<topic>` for design rounds (ADR drafting).
- **Development work:** `dev/dc<N>-<topic>` for development chunks (implementation).

Every change goes through a PR. Direct pushes to `main` are not used.

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
[redacted]        [redacted]       [redacted]
assignment    [redacted]      submission
[redacted]
```

Enforced by NFR-1 and reviewed before merge.

## ADRs

Architecture decisions land as ADRs under `docs/adr/`, numbered sequentially. Amendments to an existing ADR go in the same file under an "Amendment" heading with the date and rationale. Don't backfill ADRs to justify code — write the ADR first, then implement.
