# Contributing

## Commits

**Conventional Commits.** Subject line: `<type>(<scope>): <summary>`.

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.
Scopes follow the codebase layout: `parser`, `graph`, `input`, `analyzer`, `cli`, `schema`, `ci`, `adr`, `golden`.

Every AI-assisted commit ends with two attribution trailers (no email required):

```
AI-assistant: <tool> v<version> (<provider-note>)
Model: <api-model-identifier>
```

Concrete forms by tool:

```
# Claude Code (Opus / Sonnet)
AI-assistant: Claude Code v0.2.6 (Claude Opus 4.1 via Anthropic)
Model: claude-opus-4-1-20250514

# Google Antigravity (Gemini)
AI-assistant: Google Antigravity (Gemini 3.5 Flash via Google)
Model: gemini-3.5-flash
```

Rules:

- **No email domain guessing.** Never fabricate an email to fit the old `Co-authored-by:` pattern.
- **`Model:` value must match the API identifier** as reported by the tool (date-stamp included for audit traceability where available). Do not guess or default to generic names.
- Mixed-tool commits (rare) include both trailer pairs.
- Hand-written commits (no AI assistance) include neither trailer.

## Branching

- `main` — protected. Only merged via PR.
- **Design work:** `design/r<N>-<topic>` for design rounds (ADR drafting).
- **Development work:** `dev/dc<N>-<topic>` for development chunks (implementation).

Every change goes through a PR. Direct pushes to `main` are not used.

## Development Setup

Choose the setup section corresponding to your execution environment:

### Option A — Windows (PowerShell)

1. Install the package in editable mode with development dependencies:
   ```powershell
   python -m pip install -e ".[dev]"
   ```
2. Install the git pre-commit hooks:
   ```powershell
   python -m pre_commit install --hook-type pre-commit
   ```
   This configures the gitleaks secret scanner to run automatically on commit.

### Option B — Linux / WSL (bash)

1. Install system Python packages (if missing, required on Debian/Ubuntu systems):
   ```bash
   sudo apt-get update && sudo apt-get install -y python3-pip python3-venv
   ```
2. Install the package in editable mode with development dependencies:
   ```bash
   python3 -m pip install -e ".[dev]"
   ```
3. Install the git pre-commit hooks:
   ```bash
   pre-commit install --hook-type pre-commit
   ```

## Pre-merge checklist

All of these must be green before a PR merges:

### Windows (PowerShell)

```powershell
# lint + formatting
ruff check .
ruff format --check .

# typecheck
mypy codeograph/

# Python unit tests
python -m pytest -m "not slow and not external and not eval" --tb=short

# JVM + external tests (requires JDK to be on system PATH)
python -m pytest -m "slow or external" --tb=short

# Java parser tests
cd codeograph/parser/java
mvn test
cd ../../..
```

### Linux / WSL (bash)

```bash
make lint                                                    # ruff check + format check
make typecheck                                               # mypy strict
pytest -m "not slow and not external and not eval" --tb=short  # Python unit tests
pytest -m "slow or external" --tb=short                      # JVM + external tests (needs JDK)
cd codeograph/parser/java && mvn test                        # Java parser tests
```

CI enforces these on every push to `dev/**` and on PRs to `main`. See `.github/workflows/ci.yml`.

## Golden tests

The golden test (`tests/integration/test_goldens.py`) compares the emitted `graph.json` against checked-in goldens under `tests/golden/codeograph-corpus/`.

> [!IMPORTANT]
> **Golden-Refresh Environment:** Golden refreshes must only be performed in a Linux-matching environment (WSL, devcontainer, or CI). Never refresh or update goldens directly on Windows. Doing so introduces CRLF line endings, path separators, and JVM version differences that cause CI checks to fail.

When a deliberate change affects graph output:

1. Run `make golden-update` (or `pytest tests/integration/test_goldens.py --update-goldens` in WSL) to regenerate goldens.
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

## ADRs

Architecture decisions land as ADRs under `docs/adr/`, numbered sequentially. Amendments to an existing ADR go in the same file under an "Amendment" heading with the date and rationale. Don't backfill ADRs to justify code — write the ADR first, then implement.

## Running tests

We use `pytest` for Python tests and Maven for Java tests.
To run the fast, offline unit tests (this is the default — `addopts` in `pyproject.toml` already excludes slow/external/eval):
```bash
pytest
```
To run JVM-dependent and other external tests (requires JDK on PATH):
```bash
pytest -m "slow or external"
```
To run the full suite including eval tests:
```bash
pytest -m "slow or external or eval"
```

## Markers and when to use them

We use three `pytest` markers (defined in `pyproject.toml`, ADR-018 Fork 1):

| Marker | When to use |
|---|---|
| `slow` | Tests that take more than a few seconds |
| `external` | Tests that depend on external tools or resources (JVM, network, `npx`, `tsc`, `mvn`) |
| `eval` | Scorecard / evaluation tests |

Use these markers explicitly with `@pytest.mark.<marker>` on your test class or function. The default `pytest` invocation (and the CI `unit` job) excludes all three.

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

## Responding to a gitleaks finding

When the gitleaks check fails on your PR or in the nightly scan, follow this procedure. Do not improvise.

### Step 1 — Confirm whether this is a real secret

Real secrets:
- Live API keys, tokens, passwords, OAuth client secrets, private keys
- Database connection strings with embedded credentials
- Webhook URLs containing authentication tokens
- Anything that grants access to a system

Common false positives:
- Mock / fake credentials in test fixtures
- Placeholder values in `.env.example` files (e.g., `JWT_SECRET=replace-me`)
- Documentation examples ("here is what an AWS access key looks like")
- Generated hashes / fingerprints that coincidentally match credential patterns

### Step 2A — If REAL: rotate the credential FIRST

1. Treat the credential as compromised from the moment it was committed.
2. Generate a new credential at the provider (rotate the API key, regenerate the token, change the password, etc.).
3. Update wherever the old credential is used (env vars, deployed services, teammate machines).
4. Revoke the old credential at the provider if possible.
5. File an incident issue using `.github/ISSUE_TEMPLATE/secret-leak-incident.md` describing what was exposed and the rotation steps taken. NEVER include the rotated value in the issue.
6. Remove the value from your branch — use a placeholder, env var reference, or `.env` file (not committed).
7. Push the fix.

For nightly-scan detections, ALSO check whether the secret has been pushed to remote in the last 24 hours — the exposure window matters.

### Step 2B — If FALSE POSITIVE: add allowlist entry with reason

1. Prefer inline: add `# gitleaks:allow reason=<short-rationale>` on the line.
2. For binary / generated files: add a `.gitleaksignore` entry with a `# reason: <why>` line immediately above.
3. The PR must explain in its description why this is a false positive and what the value actually is.

### Step 3 — Do NOT do these things

- Do NOT amend the commit to hide the value (history still contains it).
- Do NOT add an allowlist entry without confirming it is a false positive.
- Do NOT bypass the gitleaks check via admin override (the repository ruleset prohibits bypass).
- Do NOT push the same credential to a different file (still exposed).
- Do NOT delete the incident issue before rotation is verified.
