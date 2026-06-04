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

## Prompt Authoring

Prompts are stored in `codeograph/prompts/` and are processed via a custom Jinja2 pipeline (ADR-014).

### Custom Delimiters
We use custom Jinja2 delimiters to avoid conflicting with source code syntax (like Java annotations `@` or standard markdown `{}`):
- Variables: `<< var_name >>`
- Blocks: `<% if condition %> ... <% endif %>`
- Comments: `<# This is a comment #>`

### Versioning and Hash Pins
Every prompt version is an immutable file (e.g., `v1.md`). When creating or modifying a prompt:
1. Include the YAML frontmatter with the `content_hash_pin` field.
2. If it's a new version, bump the filename (e.g., `v2.md`) and update the `default.yaml` alias file to point to it.
3. Our pre-commit hook automatically updates the `content_hash_pin` when you stage prompt files. If you bypass hooks, you must run `python scripts/update_prompt_hash_pins.py` manually.

Modifying an existing prompt version *changes its hash*. The loader strictly verifies the pin, and the hash becomes part of the LLM Cache Key (ADR-015), ensuring no silent staleness.

## Banned terms

A small list of terms must not appear anywhere in source, tests, docs, ADRs,
commit messages, or PR text. The canonical list lives in
[`.banned-terms.txt`](./.banned-terms.txt) — link to it rather than
restating it here.

**Enforcement:**

- **Local:** `scripts/check_banned_terms.py` runs as a pre-commit hook on
  staged files and the commit message. Install hooks once with
  `pre-commit install --hook-type pre-commit --hook-type commit-msg`.
- **CI:** the same scanner runs in `.github/workflows/ci.yml` on every push
  and pull request, scanning the full repo tree and commits in range.
- **PR text:** at present, PR titles, descriptions, and comments are NOT
  scanned automatically — they are the reviewer's responsibility. When
  the violation is found in posted PR text, the policy is to fail the
  check and require the comment be edited or deleted (not auto-redacted).
  Extending the workflow to scan PR text is tracked as a follow-up.

**Per-line exemption:** when an inherent technical term legitimately
matches (e.g., a mypy `[assignment]` error code, third-party API lifecycle
vocabulary), append `# banned-terms: ok` to that line as a pragma.
Use sparingly; rephrasing is preferred.

Enforced by NFR-1.

## ADRs

Architecture decisions land as ADRs under `docs/adr/`, numbered sequentially. Amendments to an existing ADR go in the same file under an "Amendment" heading with the date and rationale. Don't backfill ADRs to justify code — write the ADR first, then implement.

## Running tests

We use `pytest` for Python tests and Maven for Java tests.
To run the fast, offline unit tests:
```bash
pytest -m "not integration and not external"
```
To run all tests including integration tests:
```bash
pytest
```

## Markers and when to use them

We use several `pytest` markers (defined in `pyproject.toml`) to categorize tests:
- `integration`: Tests that require the JVM subprocess or a real JAR parser.
- `external`: Tests that depend on external tools like `npx`, `tsc`, or `mvn`.
- `tier1`, `tier2`, `tier3`: Golden graph tests targeting specific corpus sizes.
- `slow`: Any test taking longer than a few seconds.

Use these markers explicitly using `@pytest.mark.<marker>` on your test functions.

## Adding fixtures

- **Tiny fixtures**: Place in `tests/fixtures/llm` or `tests/fixtures/render-fixture`.
- **Integration mini-corpora**: Place small code samples directly in `tests/fixtures/corpora/`.
- **Golden graphs**: Stored alongside their respective corpora.

## Adding a corpus

When adding a new example corpus to `examples/`:
1. Include it in the `ci.yml` matrix under the `eval` job.
2. Ensure it runs deterministically (use fixed versions of dependencies).
3. Do not check in its `out/` directory; CI will generate it.

## Determinism classification

Determinism is strictly managed across the pipeline. Refer to `tests/helpers/determinism.py` for tools to freeze timestamps and UUIDs during test execution. 
All tests must pass regardless of the underlying OS or timezone (`TZ=UTC` is enforced in CI).

## Multi-OS extension procedure

To extend CI testing to macOS or Windows:
1. Open `.github/workflows/ci.yml`.
2. Locate the `strategy.matrix.os: [ubuntu-latest]` block in the relevant jobs.
3. Add `windows-latest` or `macos-latest` to the array.
4. Ensure all paths use `pathlib` or `/` separators.

## CI required checks setup (for repo admins)

Repository administrators must configure branch protection rules on `main` to require the following CI jobs to pass before merging:
- `Python (unit)`
- `Python (integration-external)`
- `Java (mvn test)`
- `Cross-corpus Eval Report`
