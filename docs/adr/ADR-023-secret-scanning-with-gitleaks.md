---
status: accepted
date: 2026-06-06
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-023 — Secret Scanning with Gitleaks

## Context and Problem Statement

FR-21 requires gitleaks secret scanning in CI on every push and pull request with merges blocked on detection. Gitleaks is already running in CI via `.github/workflows/secrets-scan.yml` (the gitleaks check produced a green status on PR #9 and prior merged PRs). This ADR formalizes what is shipped and locks the operational disciplines that v1 codifies around it: version pinning policy, allowlist mechanism for false positives, detection scope across PR events and scheduled scans, and the failure response procedure when a real secret is detected.

The scope is intentionally narrow. Gitleaks is a mature, single-purpose tool with a curated default ruleset that covers ~100 credential patterns (AWS, GCP, Azure, Stripe, JWT, generic API keys, private keys, etc.). The v1 surface is operational and procedural — not algorithmic. Decisions cover where gitleaks runs (CI mandatory + pre-commit opt-in), how the version is pinned and updated, how false positives are allowlisted, what scope each scan covers (PR-diff for events; full history for nightly), and what happens when a secret is detected.

The framework introduces no new external service dependency. The `pre-commit` Python package, the `pre-commit` git-hook framework, and gitleaks itself are all open-source, locally-installable, and operational without secret material at scan time. The repository ruleset already enforces gitleaks as a required check with no bypass mechanism; this ADR ratifies the existing posture rather than altering it.

## Decision Drivers

* **No silent failures** — every detection blocks merge (FR-21); contributor procedure is documented; allowlist entries require `reason=` annotation visible in PR diff.
* **Defense-in-depth** — pre-commit catches secrets before they enter git history; CI catches anything that slipped past; nightly catches pre-existing in history. Three layers, independent.
* **Industry-standard pattern** — `pre-commit` framework, exact-version pinning, gitleaks defaults, inline allowlist comments, scheduled full-history scans match the layout of mature OSS projects.
* **Tractable v1 implementation** — six forks (one absorbed) produce a framework that ships with one workflow file (unchanged), one new pre-commit config, one CONTRIBUTING.md section, and one runbook. No bespoke tooling.
* **Forward compatibility with v1.1** — admin bypass mechanism, automated rotation-reminder PR comments, hook-scope expansion (ruff / mypy / additional linters), and per-file rule disable are all deferred with documented triggers.
* **Realistic enterprise targets** — gitleaks default rules cover the secret patterns actually present in Java / Spring Boot projects, NestJS scaffolds, Python build artefacts, and `.env.example` files.
* **YAGNI** — vendored `.gitleaks.toml` config, automated PR comments, mandatory hook installation verification, baseline-fingerprint files at v1 ship are all explicitly out of scope.
* **Citation discipline** — version pin syntax, allowlist comment format, and scan scope all cite gitleaks documentation or established OSS practice; nothing invented.

## Considered Options

### Fork 1 — Where gitleaks runs

* (a) CI only (current shipped state, formalized); no pre-commit hook.
* (b) Pre-commit hook only; no CI scanning (violates FR-21).
* **(c) CI gate mandatory + pre-commit hook opt-in via `pre-commit install`; `.pre-commit-config.yaml` at repo root; `pre-commit` Python framework; CONTRIBUTING.md documents the install step. ✅**
* (d) CI gate + pre-commit hook with mandatory CI-side verification of hook presence.

### Fork 2 — Version pinning + configuration source

* **(a) Exact version pin in both CI workflow and `.pre-commit-config.yaml`; default rules only (no vendored `.gitleaks.toml`); CI lint check verifies pin parity; manual quarterly upgrade. ✅**
* (b) Minor-version range pin (`v8.18.x`); default rules.
* (c) Exact pin + vendored `.gitleaks.toml` extending defaults.
* (d) Latest version; vendor config from scratch.

### Fork 3 — Allowlist mechanism for false positives

* (a) `.gitleaksignore` file only; fingerprint-based.
* (b) Inline `# gitleaks:allow` comments only.
* **(c) Both mechanisms: inline `# gitleaks:allow reason=<why>` preferred for source files; `.gitleaksignore` fallback for binary / generated / third-party committed files; mandatory `reason=` annotation. ✅**
* (d) Inline comments only, strict (refactor edge cases that can't annotate).

### Fork 4 — Detection scope

* (a) PR-diff-only on push/pull_request events (current state); no scheduled scan.
* (b) Full-history scan on every PR event.
* **(c) PR-diff-only on push/pull_request + scheduled full-history scan added as new `gitleaks-full-history` job in existing `nightly.yml` workflow; redacted output; documented runbook for triage. ✅**
* (d) (c) plus committed baseline fingerprint file at v1 ship.

### Fork 5 — Failure response procedure

* **(a) Documented `CONTRIBUTING.md` "Responding to a gitleaks finding" section; rotation-first sequence; no admin bypass; matches existing ruleset `bypass_actors: []`; optional incident-issue template. ✅**
* (b) (a) plus admin emergency bypass with audit-logged justification.
* (c) (a) plus automatic PR comment with rotation steps.

### Fork 6 — Pre-commit hook framework choice

Absorbed by Fork 1's sub-rule lock (`pre-commit` Python package; https://pre-commit.com/; in `[project.optional-dependencies] dev`). No separate fork decision required.

## Decision Outcome

### Fork 1 — Where gitleaks runs: (c) CI mandatory + pre-commit opt-in

Two layers, independent, with the CI gate enforcing FR-21 and the pre-commit hook providing cheaper local prevention.

**CI gate** (shipped structure preserved; Fork 2 adds the `GITLEAKS_VERSION` env pin as the only modification this ADR introduces):

```yaml
# .github/workflows/secrets-scan.yml
name: Secret scan

on:
  push:
    branches: [main, "dev/**"]
  pull_request:
    branches: [main]

jobs:
  gitleaks:
    name: gitleaks
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
        with:
          # Full history required so gitleaks can scan every commit,
          # not just the files changed in this push.
          fetch-depth: 0
      - name: Run gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_VERSION: "8.30.1"    # Fork 2 pin — added by ADR-023
```

**Pre-commit hook** (NEW, opt-in):

```yaml
# .pre-commit-config.yaml at repo root
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1                        # Fork 2: same exact pin as CI
    hooks:
      - id: gitleaks
```

```toml
# pyproject.toml — pre-commit added to dev deps
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff",
    "mypy",
    "pre-commit",                       # NEW
    # ...
]
```

**Contributor onboarding** (CONTRIBUTING.md):

```bash
pip install -e ".[dev]"
pre-commit install                      # one-time; installs the git hook
```

**Bypass policy:** `git commit --no-verify` is permitted but discouraged. CI catches anything that bypasses the hook. No in-repo enforcement that contributors must have the hook active (verification is not possible from CI without running the same scan).

**Pre-commit scope:** staged files only (gitleaks default for the pre-commit hook); never full history at commit time (would be prohibitively slow per commit).

**Future additional hooks** (ruff format, mypy, banned-terms grep, etc.) are out of scope for ADR-023 and can be added as orthogonal `.pre-commit-config.yaml` entries in a future ADR or PR.

### Fork 2 — Version pinning + configuration source: (a) exact pin + defaults

**Exact version pin** in both locations:

| Location | Field | Format |
|---|---|---|
| `.github/workflows/secrets-scan.yml` | `env.GITLEAKS_VERSION` | `"8.30.1"` (exact; no `v` prefix per action convention) |
| `.pre-commit-config.yaml` | `repos[].rev` | `v8.30.1` (exact; `v` prefix per gitleaks tag convention) |

**Pin parity CI check** — added to the `lint` job (parallel to ADR-014 / ADR-017 / ADR-022 freshness gates):

```yaml
# .github/workflows/ci.yml — lint job — additional step
- name: Verify gitleaks version pin parity
  shell: bash
  run: python -m codeograph.scripts.verify_gitleaks_pin
```

The verifier reads both files, parses the version strings (stripping the `v` prefix where present), and exits non-zero on mismatch. Implementation is a single short script under `codeograph/scripts/`.

**Default rules source** — gitleaks built-in only. No `.gitleaks.toml` at repo root in v1.

**Adding `.gitleaks.toml` later** — permitted as an additive change when a real custom rule or `[extend]` discipline emerges. Not an ADR-023 amendment required; the file's presence is documented in PR review.

**Upgrade cadence:**

| Trigger | Action |
|---|---|
| Quarterly review | Maintainer checks gitleaks release notes; if non-trivial changes, opens a version-bump PR |
| Gitleaks CVE / security advisory | Immediate version-bump PR |
| Gitleaks-action release | Independent; `gitleaks/gitleaks-action@v2` major-version float allowed; binary version pinned via `GITLEAKS_VERSION` env |

**Never auto-upgrade.** Renovate / Dependabot can be configured later (operational concern, not an ADR decision); v1 ships manual.

### Fork 3 — Allowlist mechanism: (c) both, inline preferred

**Inline allowlist comment** (preferred for source files):

```python
# tests/fixtures/llm/mock_provider.py
MOCK_API_KEY = "sk-test-1234567890abcdef"  # gitleaks:allow reason=mock-llm-test-fixture

class MockAnthropicResponse:
    """Stub response shape."""
    # gitleaks:allow reason=docstring-example
    EXAMPLE_API_KEY_DOC = "sk-ant-api03-..."
```

```bash
# examples/spring-rest-sample/.env.example
JWT_SECRET=replace-me-with-a-real-secret-in-production  # gitleaks:allow reason=env-example-placeholder
```

**`.gitleaksignore`** (fallback for binary / generated / third-party files):

```
# .gitleaksignore at repo root
# Each entry MUST be preceded by a `# reason: <why>` line.

# reason: binary EXIF metadata matches generic-api-key pattern by coincidence
4f8a1b...  examples/spring-rest-sample/assets/logo.png:0  generic-api-key

# reason: third-party committed fixture; cannot edit upstream
9c2e3d...  tests/fixtures/corpora/lombok_dtos/src/...:42  jwt-token
```

**Mandatory `reason=` annotation** is enforced by review discipline (no PR with a new allowlist entry merges without the reason being legitimate). No automated tooling enforces this in v1; manual review is the gate.

**Policy by file kind:**

| File kind | Mechanism |
|---|---|
| Source code (`.py`, `.ts`, `.java`, `.yml`, `.json`, `.toml`, `.md`) | Inline `# gitleaks:allow reason=<why>` |
| Binary (`.png`, `.jpg`, `.zip`, `.dat`) | `.gitleaksignore` with `# reason:` |
| Generated (`codeograph/_generated/*`) | `.gitleaksignore` with `# reason:` |
| Third-party committed | `.gitleaksignore` with `# reason:` |

**Initial v1 `.gitleaksignore`** ships empty (no entries). Inline allowances are added as test fixtures and example corpora are committed.

**Banned-terms list interaction:** the AGENTS.md banned-terms grep is independent of gitleaks; inline `gitleaks:allow` does NOT exempt a line from the banned-terms discipline. Both apply.

**No mass-allowlist commits** — a PR adding more than 10 allowlist entries at once is suspicious; reviewer treats it as an audit trigger.

### Fork 4 — Detection scope: (c) PR-diff + scheduled full-history

**PR-event scan** (existing; unchanged):

```yaml
# .github/workflows/secrets-scan.yml — unchanged
on: [push, pull_request]
```

Gitleaks-action default behavior: scans the PR diff against base; full clone via `fetch-depth: 0` so diff resolution is correct.

**Scheduled full-history scan** (NEW in `nightly.yml`):

```yaml
# .github/workflows/nightly.yml — ADD a new job alongside existing nightly jobs
jobs:
  gitleaks-full-history:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_VERSION: "8.30.1"
        with:
          args: detect --source . --no-banner --redact
      - if: failure()
        run: |
          echo "::error::Full-history gitleaks scan detected secrets — see CONTRIBUTING.md 'Responding to a gitleaks finding'"
```

**`--redact`** ensures the detected secret value is masked in CI logs (the rule id, file path, and line number are visible; the actual secret value is not).

**Scheduled scan failure handling:**
- Job fails red on detection
- Does NOT block any PR merges (scheduled jobs are not part of merge gating)
- Default GitHub Actions failure notifications email the repo owner
- Maintainer triages per the Fork 5 runbook

**Initial nightly baseline** — the maintainer runs the nightly job manually before relying on the scheduled cadence to establish a clean baseline. If findings surface, the maintainer addresses them (per Fork 5) before the first scheduled run.

**Pre-commit scope unchanged** — staged files only (gitleaks default for the pre-commit hook).

### Fork 5 — Failure response procedure: (a) documented procedure, no bypass

**`CONTRIBUTING.md`** section "Responding to a gitleaks finding":

```markdown
# Responding to a gitleaks finding

When the gitleaks check fails on your PR or in the nightly scan, follow this
procedure. Do not improvise.

## Step 1 — Confirm whether this is a real secret

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

## Step 2A — If REAL: rotate the credential FIRST

1. Treat the credential as compromised from the moment it was committed.
2. Generate a new credential at the provider (rotate the API key, regenerate
   the token, change the password, etc.).
3. Update wherever the old credential is used (env vars, deployed services,
   teammate machines).
4. Revoke the old credential at the provider if possible.
5. File an incident issue using `.github/ISSUE_TEMPLATE/secret-leak-incident.md`
   describing what was exposed and the rotation steps taken.
   NEVER include the rotated value in the issue.
6. Remove the value from your branch — use a placeholder, env var reference,
   or `.env` file (not committed).
7. Push the fix.

For nightly-scan detections, ALSO check whether the secret has been pushed to
remote in the last 24 hours — the exposure window matters.

## Step 2B — If FALSE POSITIVE: add allowlist entry with reason

1. Prefer inline: add `# gitleaks:allow reason=<short-rationale>` on the line.
2. For binary / generated files: add a `.gitleaksignore` entry with a
   `# reason: <why>` line immediately above.
3. The PR must explain in its description why this is a false positive and
   what the value actually is.

## Step 3 — Do NOT do these things

- Do NOT amend the commit to hide the value (history still contains it).
- Do NOT add an allowlist entry without confirming it is a false positive.
- Do NOT bypass the gitleaks check via admin override (the repository
  ruleset prohibits bypass).
- Do NOT push the same credential to a different file (still exposed).
- Do NOT delete the incident issue before rotation is verified.
```

**Repository ruleset state** (matches current shipped state):
- `bypass_actors: []`
- `current_user_can_bypass: never`

No admin emergency bypass mechanism in v1. The ruleset's no-bypass configuration is ratified by this ADR.

**Incident-issue template** at `.github/ISSUE_TEMPLATE/secret-leak-incident.md` with structured fields:
- What was exposed (credential type, not value)
- Rotation steps taken
- Services / teams notified
- Whether history scrub was performed
- Closed when rotation is verified

**Real-secret history scrub** is the maintainer's discretionary action; not mandated. Rotation is the primary requirement.

**Communication to downstream consumers** is outside ADR-023 scope — the project has no committed downstream consumer surface in v1.

### Constraint flagged for ADR-022

The pin-parity check (Fork 2) joins the freshness-gate family established by ADR-014 (prompt freshness), ADR-017 Fork 1 (scorecard schema), and ADR-022 Fork 7 (manifest schema). All four checks live in the `lint` job (ADR-018 Fork 6); the verifier scripts share a similar shape (read file, compute expected, compare, exit non-zero on mismatch).

### Constraint flagged for ADR-018

The pre-commit framework adds `pre-commit` to `[project.optional-dependencies] dev` in `pyproject.toml`; ADR-018 Fork 4's coverage scope (`source = ["codeograph"]`) excludes the `pre-commit` package from coverage measurement, which is the correct behavior.

### Constraint flagged for v1.1 — admin emergency bypass

An admin bypass mechanism is explicitly deferred. The v1.1 trigger is "a real false-positive class that the inline allowlist + `.gitleaksignore` mechanisms cannot handle within ~1 hour of detection AND that blocks a time-sensitive release." When (if) that materializes, the v1.1 ADR amending Fork 5 will lock the bypass actor list, the audit-issue requirement, and the post-bypass review obligation.

## Consequences

**Positive.**
1. Defense-in-depth at minimal cost — pre-commit catches secrets before history; CI catches anything that slipped past; nightly catches pre-existing.
2. Exact version pinning + pin-parity CI check eliminates the "Tuesday passed; Wednesday fails on the same content" failure mode.
3. Default rules cover the realistic threat surface; no vendored config maintenance burden in v1.
4. Inline allowlist comments make false-positive exceptions visible in PR diffs; reviewers see exactly what is being whitelisted and why.
5. Rotation-first procedure prevents the worst-case failure (allowlisting a real secret to unblock a merge).
6. No admin bypass matches the repository ruleset's existing posture; ADR ratifies rather than alters.
7. Operational surface is bounded — one unchanged CI workflow, one new pre-commit config, one new nightly job, one new lint step, one CONTRIBUTING.md section, one optional issue template.
8. Forward path to v1.1 is clean — admin bypass, hook scope expansion, baseline fingerprints, auto-PR-comment automation all have documented triggers.

**Negative.**
1. Manual quarterly version-bump PRs are operational overhead; missed quarters mean the project drifts behind security patches.
2. Two pin locations (CI workflow + `.pre-commit-config.yaml`) require parity discipline; the CI check catches drift but adds workflow surface.
3. No admin bypass means a confirmed false positive that gitleaks misses (no Fork 3 mechanism handles it cleanly) can block a release until either the rule is disabled (requires vendored `.gitleaks.toml` per Fork 2 deferred path) or the file is refactored. v1.1 bypass mechanism is the relief valve.
4. Pre-commit hook is opt-in; contributors who skip `pre-commit install` lose the local layer. CI catches them but the cheaper local feedback is missed.
5. Nightly scan triage assumes maintainer monitors GitHub Actions failure notifications; without that monitoring, a pre-existing finding sits undetected.
6. Inline `gitleaks:allow reason=` discipline is review-enforced, not tool-enforced; an inattentive reviewer may approve an allowance without challenging the reason.
7. The CI lint step's pin-parity check is one more thing that can fail; a contributor updating only one of the two pin locations sees a CI failure and must remediate.
8. Default-rules-only means a project-specific secret pattern (none exist in v1) would not be caught until the rule is added — which requires the vendored config path Fork 2 deferred.

## Confirmation

1. The `.github/workflows/secrets-scan.yml` workflow file exists, runs on push and pull_request events, uses `gitleaks/gitleaks-action@v2`, and produces a status check named `gitleaks` (verified by inspecting the workflow file plus the GitHub Actions status on any PR).
2. The `.pre-commit-config.yaml` file exists at repo root with one entry whose `repo` field is `https://github.com/gitleaks/gitleaks` and whose `rev` matches the `GITLEAKS_VERSION` in `secrets-scan.yml` (verified by the pin-parity CI lint step).
3. Running `pip install -e ".[dev]"` followed by `pre-commit install` succeeds and creates a `.git/hooks/pre-commit` file (verified by contributor onboarding test or manual `--help` inspection).
4. Attempting to commit a file containing a string matching the gitleaks `generic-api-key` rule with the pre-commit hook installed causes `git commit` to fail with a gitleaks error referencing the line (verified by integration test using a fixture file in a temp git repo).
5. Adding `# gitleaks:allow reason=test-fixture` on the same line as the offending string causes the hook (or CI scan) to pass that line (verified by integration test).
6. Running `gitleaks detect --source . --no-banner --redact` locally on a clean main branch exits 0 with no findings (verified by running locally; if it fails on the initial run, findings must be addressed per Fork 5 before relying on the scheduled scan).
7. The `.github/workflows/nightly.yml` workflow contains a `gitleaks-full-history` job that runs gitleaks with `--source .` against the full clone (verified by inspecting the workflow file).
8. The `CONTRIBUTING.md` file contains a section titled "Responding to a gitleaks finding" with the three-step structure (confirm → rotate-or-allowlist → don't) (verified by visual inspection or a markdown-heading grep).
9. The repository ruleset `protect-main` has `bypass_actors: []` and `current_user_can_bypass: never` (verified by `gh api repos/<owner>/<repo>/rulesets/<id>`).
10. The pin-parity check (`python -m codeograph.scripts.verify_gitleaks_pin`) exits 0 when both pins match and exits non-zero when they differ (verified by unit test of the verifier script).
11. The initial `.gitleaksignore` at repo root is empty or contains only header comments — no fingerprint entries shipped in v1 (verified by file inspection).
12. The `pyproject.toml` `[project.optional-dependencies] dev` block includes `pre-commit` (verified by `grep pre-commit pyproject.toml`).

## Pros and Cons of the Considered Options

### Fork 1 — Where gitleaks runs

**(a) CI only (current state, formalized).**
* Good, because matches what's already shipped; minimal change.
* Good, because zero contributor onboarding friction.
* Good, because single source of truth for secret detection.
* Bad, because secrets that reach CI have already entered the contributor's branch history.
* Bad, because force-push remediation after a CI-caught secret is messier than pre-commit prevention.

**(b) Pre-commit hook only.**
* Bad, because it violates FR-21 explicitly.
* Bad, because a contributor using `git commit --no-verify` lands secrets unchallenged.

**(c) CI mandatory + pre-commit opt-in. ✅ Chosen.**
* Good, because defense-in-depth — two independent layers.
* Good, because honors FR-21 fully (CI scanning unchanged).
* Good, because pre-commit prevents secrets from entering git history in the first place.
* Good, because `pre-commit` framework is the de-facto Python standard.
* Good, because opt-in `pre-commit install` keeps onboarding step explicit.
* Bad, because one onboarding step contributors may skip.
* Bad, because `pre-commit` framework adds a dev dependency.

**(d) CI mandatory + pre-commit with CI-side verification.**
* Good, because hook presence cannot be silently removed.
* Bad, because verifying the config file's presence doesn't prove the hook actually executed.
* Bad, because adds CI surface for a check that doesn't change the security property.

### Fork 2 — Version pinning + configuration source

**(a) exact pin + defaults. ✅ Chosen.**
* Good, because reproducible — same version everywhere.
* Good, because maintainer controls upgrades.
* Good, because default rules cover the realistic threat surface.
* Good, because no vendored config to maintain.
* Bad, because manual version-bump PRs are operational overhead.
* Bad, because two pin locations require parity discipline.

**(b) minor-version range pin.**
* Good, because patch-level security updates land automatically.
* Bad, because different machines may see different patch versions.
* Bad, because reproducibility weakened.

**(c) exact pin + vendored extending config.**
* Good, because reproducible AND customizable.
* Good, because allowlist can live in config.
* Bad, because vendored file is one more thing to maintain.
* Bad, because no custom rules needed in v1 — file ships nearly empty.

**(d) latest version + vendored scratch config.**
* Bad, because unpinned latest reproduces "passes Tuesday, fails Wednesday".
* Bad, because config-from-scratch abandons curated defaults; substantial maintenance.

### Fork 3 — Allowlist mechanism

**(a) `.gitleaksignore` only.**
* Good, because gitleaks-native; one canonical mechanism.
* Good, because one file collects all allowlist entries.
* Bad, because fingerprints are opaque to reviewers.
* Bad, because generating fingerprints requires running gitleaks locally first.
* Bad, because fingerprint changes when file content changes — refactor-unstable.

**(b) Inline comments only.**
* Good, because per-line context visible in PR diff.
* Good, because reviewer reads the comment and knows what's whitelisted.
* Good, because refactor-stable.
* Bad, because binary / generated files cannot be inline-annotated.

**(c) both, inline preferred. ✅ Chosen.**
* Good, because defense-in-depth — every false-positive source has an idiomatic mechanism.
* Good, because inline preference keeps most allowlist decisions visible in PR diffs.
* Good, because `.gitleaksignore` stays small (only edge cases).
* Good, because both mechanisms work in CI and pre-commit identically.
* Bad, because two mechanisms to document; policy guidance in CONTRIBUTING.md prevents confusion.

**(d) Inline only, strict.**
* Good, because strictest discipline.
* Bad, because edge cases (binary fixtures) become un-allowlistable without vendored config.
* Bad, because refactoring committed fixtures to dodge gitleaks is wrong-prioritization.

### Fork 4 — Detection scope

**(a) PR-diff only (current state).**
* Good, because matches current shipped state.
* Good, because fast.
* Bad, because misses pre-existing secrets in history.
* Bad, because no audit-trail confidence that full history is clean.

**(b) Full-history on every PR.**
* Good, because maximum thoroughness.
* Bad, because repeats full-history scan on every PR.
* Bad, because slow.
* Bad, because already-merged commits' contents are immutable; re-confirming them every PR is wasteful.

**(c) PR-diff + scheduled full-history. ✅ Chosen.**
* Good, because catches both failure modes with no wasted CI per PR.
* Good, because reuses existing `nightly.yml` workflow substrate.
* Good, because standard belt-and-suspenders pattern adopted by mature OSS projects.
* Good, because bounded CI cost.
* Bad, because nightly triage path requires maintainer monitoring.

**(d) (c) + baseline fingerprint file.**
* Good, because establishes a clean baseline.
* Bad, because adds operational overhead at v1 ship.
* Bad, because risks "we just allowlisted everything to ship" anti-pattern.

### Fork 5 — Failure response procedure

**(a) documented procedure, no bypass. ✅ Chosen.**
* Good, because no-bypass matches the existing ruleset state.
* Good, because rotation-first is the load-bearing discipline.
* Good, because real vs false-positive criteria are documented.
* Good, because Fork 3's allowlist mechanism is the right tool for false positives.
* Good, because no automation in v1 keeps the runbook authoritative.
* Bad, because no relief valve for unforeseeable false-positive blockers.

**(b) (a) + admin emergency bypass with audit.**
* Good, because provides relief valve for edge cases.
* Bad, because bypass is the dangerous path — maintainer under pressure may bypass when they shouldn't.
* Bad, because v1 has no emergency-release pressure justifying the bypass mechanism.

**(c) (a) + automatic PR comment with rotation steps.**
* Good, because reduces "I don't know how to rotate this" friction.
* Bad, because comment automation is brittle — provider rotation docs change.
* Bad, because adds CI / Action complexity.

## More Information

### Relationships

* **ADR-001** (project skeleton) — `pyproject.toml` `[project.optional-dependencies] dev` is the location for the `pre-commit` package addition; CI workflow YAML is AI-permitted boilerplate.
* **ADR-014** (prompt versioning) — prompt-freshness CI gate is the precedent for the pin-parity CI gate Fork 2 introduces.
* **ADR-017 Fork 1** (eval scorecard JSON Schema) — scorecard-schema freshness CI gate is another precedent for the pin-parity pattern; all four gates (prompt freshness, scorecard schema, manifest schema, gitleaks pin parity) live in the `lint` job.
* **ADR-018** (test strategy with pytest) — `pre-commit` package added to dev deps; `pre-commit install` documented in CONTRIBUTING.md; CI workflow's `lint` job hosts the pin-parity check.
* **ADR-022** (run manifest + structured logging) — manifest-schema freshness CI gate is the most recent precedent; ADR-023's pin-parity check follows the same operational pattern.
* **AGENTS.md banned-terms list** — independent of gitleaks; both disciplines apply to PRs; gitleaks does not exempt banned-terms checks.

### Deferred items

* **Admin emergency bypass mechanism** — v1.1 trigger: a confirmed false-positive class that inline + `.gitleaksignore` mechanisms cannot handle within ~1 hour AND that blocks a time-sensitive release.
* **Vendored `.gitleaks.toml`** — additive; permitted when a real custom rule or `[extend]` discipline is needed.
* **Automatic PR comment with rotation steps** — v1.1 if the documented runbook proves insufficient for contributors.
* **Hook scope expansion** (ruff format, mypy, banned-terms grep, additional pre-commit hooks) — orthogonal; can be added to `.pre-commit-config.yaml` in a future PR without an ADR amendment.
* **Renovate / Dependabot configuration for automated gitleaks version bumps** — operational; not a v1 ADR concern.
* **Baseline fingerprint file at v1 ship** — explicitly rejected; v1 ships with empty `.gitleaksignore`. If nightly scan surfaces findings, address them rather than allowlisting.
* **Communication to downstream consumers on incident** — outside v1 scope (no committed downstream consumer surface).
* **History scrub (force-push) automation** — manually executed at maintainer discretion; not automated.

### Open Questions / Future Work

* Will manual quarterly version-bump PRs actually happen, or will gitleaks drift months behind upstream? If the latter, Renovate or Dependabot becomes a real candidate.
* Will the pin-parity check catch real drift, or sit idle? Healthy if idle; if it fires, the failure mode it caught was real.
* Will the runbook's three-step structure prove sufficient for contributors who haven't encountered gitleaks before, or will additional automation prove necessary?
* Will the inline `gitleaks:allow reason=` discipline survive review pressure, or will reviewers approve unsubstantiated entries?
* Will the scheduled full-history scan surface any pre-existing findings on the first run, or is the baseline already clean?
* Will the no-bypass policy create real friction (a blocking false positive with no inline solution), motivating v1.1 bypass infrastructure?

### References

* Gitleaks documentation — https://github.com/gitleaks/gitleaks
* Gitleaks-action — https://github.com/gitleaks/gitleaks-action
* pre-commit framework — https://pre-commit.com/
* GitHub Repository Rulesets — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets
* MADR template — https://github.com/adr/madr
