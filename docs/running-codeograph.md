# Running Codeograph — pipeline & command reference

This is the "what runs when, in what order, and what do I actually type" reference. For **which
model/provider to pick and what it costs**, see
[`docs/model-selection-and-cost.md`](model-selection-and-cost.md) instead — this file is about
prerequisites, pipeline stages, CLI commands, and troubleshooting, not model choice.

> **Invocation note.** `codeograph <cmd>` and `python -m codeograph <cmd>` are equivalent. This
> doc uses `python -m codeograph` in runnable examples because the bare `codeograph` entry point
> is only on `PATH` if your install put its `Scripts`/`bin` directory there — `python -m` always
> works from an editable install. Shell-specific lines are marked `# bash/WSL` vs `# PowerShell`;
> the log-watching commands in [§6](#6-troubleshooting) are bash/WSL (`ls -t`, `tail -f`) — see
> that section for the Windows-PowerShell equivalents.

---

## 1. Prerequisites

### 1.1 Java (the AST parser sidecar)

Every `codeograph run` invocation — **including `--ast-only`** — launches a bundled JavaParser
sidecar over the JVM to produce an accurate AST. There is no way to skip this step; `--ast-only`
only skips the *LLM* passes, not the parser.

- **Java 17+ required for full-fidelity parsing.** Without a working `java` on `PATH`
  (or `JAVA_HOME` pointing at one), Codeograph does **not** fail the run — it silently falls back
  to a regex-based extractor per file, which is markedly less accurate (no resolved types, no
  complexity metrics, coarser stereotype detection). This is easy to miss: the run *succeeds*, but
  every node in `graph.json` reports `"extraction_mode": "regex_fallback"` instead of `"ast"`.
- **Always check this after a run**, especially the first one in a new shell or CI environment.
  `graph.json` is written single-line-compact by Pass 0 (and re-written pretty-printed by Pass 2),
  so a line-counting `grep -c` is unreliable — use a format-independent check instead:
  ```bash
  python -c "import json,collections;print(collections.Counter(n.get('extraction_mode') for n in json.load(open('<out-dir>/graph.json'))['nodes'] if 'extraction_mode' in n))"
  ```
  A healthy result is e.g. `Counter({'ast': 6})`. If you see any `'regex_fallback'` entries, Java
  wasn't reachable from the process that ran `codeograph`. (Only type-declaration nodes — classes,
  interfaces, enums, records — carry `extraction_mode`; methods and fields don't, hence the guard.)
- **Verify Java is actually visible to the exact process you're about to run in**, not just "some
  terminal on this machine" — `JAVA_HOME`/`PATH` are per-shell, and a shell that inherited a stale
  or misconfigured environment (e.g. a leading/trailing whitespace character accidentally baked
  into a system environment variable) can cause `shutil.which()`-style resolution to fail even
  though `java -version` works fine when you type it by hand in that same window. If you've just
  changed `JAVA_HOME` or `PATH` at the system level, open a **new** shell before trusting it —
  already-open shells and already-running tool sessions keep their old environment.
  ```bash
  java -version   # must print a real version string, not "command not found"
  ```

### 1.2 Python environment

```bash
pip install -e ".[dev]"
```
installs Codeograph plus all dev/test dependencies (pytest, ruff, mypy, etc.) in one shot from the
repo root.

### 1.3 LLM provider configuration (`.env`)

Copy `.env.example` to `.env` (gitignored — never commit real keys) and fill in **one** of the
provider blocks below. `CODEOGRAPH_LLM_PROVIDER` selects which block is active; unused blocks can
stay commented out or absent.

**Anthropic (native provider):**
```bash
CODEOGRAPH_LLM_PROVIDER=anthropic
CODEOGRAPH_ANTHROPIC_API_KEY=sk-ant-...
CODEOGRAPH_LLM_MODEL=claude-sonnet-4-6
```

**OpenRouter (aggregator — DeepSeek, Qwen, Llama, etc., all through one key):**
```bash
CODEOGRAPH_LLM_PROVIDER=openrouter
CODEOGRAPH_OPENROUTER_API_KEY=sk-or-v1-...
CODEOGRAPH_LLM_MODEL=deepseek/deepseek-v4-flash
```
The model id must be the **exact** string the provider uses (check the provider's own model/pricing
page) — a fictional or slightly-wrong id (e.g. an invented `-free` or version suffix) won't error
loudly; it just means the pre-flight cost estimate can't find a price and reports "unavailable,"
and the real API call may 404. When in doubt, confirm the id and price directly on the provider's
site rather than guessing.

**Any other OpenAI-compatible endpoint** (Gemini via Google's OpenAI-compat surface, Groq,
DeepSeek's own direct API, self-hosted, etc.):
```bash
CODEOGRAPH_LLM_PROVIDER=openai_compatible
CODEOGRAPH_OPENAI_COMPAT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
CODEOGRAPH_OPENAI_COMPAT_API_KEY=...
CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL=google-free
CODEOGRAPH_LLM_MODEL=gemini-2.5-flash
```
`CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL` is what ties this endpoint to a price-table row in
`codeograph/llm/prices.toml` (falls back to a host-derived label if omitted) — see
`docs/model-selection-and-cost.md` for the full label-to-price mapping.

### 1.4 Concurrency — turn it down for free-tier providers

`CODEOGRAPH_LLM_CONCURRENCY` (default `5`) caps how many LLM calls run in parallel. Free-tier and
low-rate-limit providers (many free OpenRouter routes, Gemini's free tier, etc.) often cap
requests-per-minute low enough that the *default* concurrency alone will trip rate limits
immediately — concurrency only bounds parallelism, it does not pace requests over time. If you're
on a free or low-quota tier:
```bash
export CODEOGRAPH_LLM_CONCURRENCY=1        # bash/WSL
$env:CODEOGRAPH_LLM_CONCURRENCY = "1"      # PowerShell
```
This won't eliminate rate-limit hits on a sufficiently tight quota, but it removes the
simultaneous-burst failure mode, which is the one concurrency actually controls. See
[§6 Troubleshooting](#6-troubleshooting) for what a rate-limited run looks like from the outside.

### 1.5 Everything else — `config.yaml`

`.env` holds secrets and the provider/model they pair with; **every other non-secret knob** lives
in `config.yaml` (loaded from the current working directory, lowest priority — env and `.env` always
override it). The committed `config.yaml` is a fully-commented catalogue of every tweakable setting
with its default: per-stage model overrides, `llm_concurrency`, `max_pass1_failure_ratio`, the cost
ceilings, cache limits, and the parser JAR path. Uncomment what you need. The settings-resolution
precedence, highest wins, is:

```
CLI flags / init kwargs  >  environment variables  >  .env  >  config.yaml  >  built-in defaults
```

Any field in `config.yaml` also has an environment-variable form, `CODEOGRAPH_<FIELD_NAME>`
(e.g. `llm_concurrency` → `CODEOGRAPH_LLM_CONCURRENCY`) — that's what the `export ...` /
`$env:...` lines elsewhere in this doc are setting. **Never put API keys in `config.yaml`** — those
are `.env`/environment only.

---

## 2. The stages

| Stage | What it does | Command | Reads | Writes | Needs an LLM? |
|---|---|---|---|---|---|
| **Pass 0** — parse + graph build | AST parse of the corpus → deterministic graph | `codeograph run` (always runs) | source corpus | `graph.json`, `manifest.json` | No (but needs Java — §1.1) |
| **Pass 1** — per-class annotation | One LLM call per class: domain label, summary, migration hazards | `codeograph run` (skipped by `--ast-only`) | `graph.json` | `llm-annotations.json` | Yes |
| **Pass 2** — corpus synthesis | One LLM call: cross-domain synthesis over all Pass-1 output | same `run` invocation, same flag | Pass-1 output | folded into `llm-annotations.json` | Yes |
| **Render** | Translates selected classes into idiomatic target-language source (full logic, not skeletons) + a deterministic project scaffold | `codeograph render` (**separate command**) | a prior `run`'s `graph.json` + `llm-annotations.json` | target-language project (e.g. `.ts` files, `package.json`) | Yes — one call per selected class |
| **Eval** | Deterministic + code-quality scorecard checks against a run's output | `codeograph eval run` (or `run --eval`) | a run's output directory | `evals/*.json` scorecards | No |

**The one structural fact that matters:** `run` bundles Pass 0, and (unless `--ast-only`) Pass 1 +
Pass 2 together — there is no flag to do Pass 1 without Pass 2, or vice versa. `render` and `eval`
are always separate commands that read a *completed* `run` output directory; they cannot run first.

---

## 3. The order, if running back to back

```
run  (Pass 0 → Pass 1 → Pass 2 → optional --eval)
  │
  └──▶ render  (reads the run's graph.json + llm-annotations.json)
             │
             └──▶ eval  (optional re-check, or use `run --eval` to fold it in up front)
```

This order is **forced by data dependency**, not a preference — `render` and `eval` literally read
files that only exist after `run` has produced them.

---

## 4. The four ways to run it — exact commands

### A. AST-only — parse only, zero LLM calls, no API key needed

```bash
python -m codeograph run <input> --out <dir> --ast-only
```
Confirms parsing + the JVM sidecar work. Check `manifest.json` for `"llm_skipped": true` and that
`graph.json` shows `extraction_mode: "ast"` (not `"regex_fallback"` — see §1.1). This is the
right first command to run against any new corpus or in any new environment, before spending a
single LLM call.

### B. Full LLM run — Pass 0 + 1 + 2, no rendering, with the cost-safety net on

```bash
python -m codeograph run <input> --out <dir> --max-llm-calls 40 --llm-call-confirm-threshold 1
```
`--llm-call-confirm-threshold 1` forces the pre-flight estimate + confirmation prompt on every run
(default threshold is 100 — a small corpus's real call count can slip under that unnoticed);
`--max-llm-calls` is a hard abort ceiling. Both are optional but strongly recommended until you
trust a given provider/corpus combination. See `docs/model-selection-and-cost.md` for the full
cost-safety-floor design (ADR-027).

On a free-tier or low-quota provider, also set `CODEOGRAPH_LLM_CONCURRENCY=1` (§1.4) before this
command — otherwise expect rate-limit retries, which are visible in the console as `WARNING` lines
and can add real wall-clock time (this is expected behavior, not a hang — see §6).

### C. Render only — from an already-completed `run`

```bash
python -m codeograph render --from <dir> --out <ts-dir> --target typescript
```
`--from` must point at a directory containing `graph.json`, `llm-annotations.json`, and
`manifest.json` from a **prior, completed** `run` (not `--ast-only` — there'd be no annotations to
render from). This is a fully separate command and a fully separate set of LLM calls; it does not
re-run Pass 0/1/2. **Important — `render`'s cost-safety story is thinner than `run`'s:** it has
**no** pre-flight cost estimate, **no** confirmation prompt, and **no** `--max-llm-calls` CLI flag.
It *does* still honor a hard ceiling via environment variables, though — set
`CODEOGRAPH_MAX_LLM_CALLS` (and/or `CODEOGRAPH_MAX_TOKENS_TOTAL`) before the command and the render
provider aborts once the ceiling is hit, exactly as `run` does:
```bash
export CODEOGRAPH_MAX_LLM_CALLS=50        # bash/WSL
$env:CODEOGRAPH_MAX_LLM_CALLS = "50"      # PowerShell
```
So the safety levers for `render` are: `CODEOGRAPH_MAX_LLM_CALLS` (hard ceiling, env-var only),
`--max-classes-per-domain` (bounds how many classes get selected in the first place, below), and
`CODEOGRAPH_LLM_CONCURRENCY`.

Useful flags:
- `--max-classes-per-domain N` — overrides the default per-domain-group render budget (**default:
  3**). Classes beyond the cap are silently excluded from output by the ADR-009 selection ladder —
  if a repository interface or DTO you expected to see isn't in the rendered output, this is very
  likely why. Raise it (e.g. `--max-classes-per-domain 20`) to render everything in a small corpus.
- `--db-layer` — persistence-layer translation strategy override. Currently the only implemented
  value is `typeorm`; ADR-010 describes a fuller `typeorm_2tier`/`typeorm_only`/`raw_only` design
  but only the single TypeORM mode is wired up today.
- `--no-scaffold` — skip emitting `package.json`/`tsconfig.json`/etc., just the translated source.
- `--list-targets` — print registered renderer targets and exit (currently: `typescript`).

### D. Everything back to back — parse → LLM → render → eval

```bash
python -m codeograph run <input> --out <dir> --eval --max-llm-calls 40 --llm-call-confirm-threshold 1
python -m codeograph render --from <dir> --out <ts-dir> --target typescript
```
`--eval` folds evaluation into the `run` step itself — no separate `eval` invocation is needed
unless you want to re-check the same output later (`codeograph eval run <dir>`).

---

## 5. Re-running into the same output directory

`--force` on `run` **clears** the output directory first (so it always contains exactly one run's
artefacts) rather than merging into whatever is already there. The same applies to `render --force`.
Without `--force`, both commands refuse to write into a non-empty directory.

---

## 6. Troubleshooting

### 6.1 "It's been sitting there for minutes — is it hung?"

Usually not. Once a rate-limited call is classified as transient (429/5xx), the retry layer waits
out the provider's own stated `Retry-After` hint rather than a fixed short backoff — on a tight
free-tier quota this can legitimately mean multi-minute waits *per node*, especially with
`CODEOGRAPH_LLM_CONCURRENCY=1`. Before assuming a hang, check the live telemetry log for the run —
it's appended to in real time, so you can see whether it's actually progressing:

The telemetry directory is `<cache_dir>/telemetry/`, where `<cache_dir>` defaults to
`~/.codeograph/cache` (`C:\Users\<you>\.codeograph\cache` on Windows; override with
`CODEOGRAPH_CACHE_DIR`). Each `run` writes `run-<run-id>.jsonl`; each `render` writes
`render-<target>-<run-id>.jsonl` in the same folder.

```bash
# bash/WSL
ls -t ~/.codeograph/cache/telemetry/run-*.jsonl | head -1     # find the current run's log
tail -f ~/.codeograph/cache/telemetry/run-<run-id>.jsonl       # watch it live
```
```powershell
# PowerShell
Get-ChildItem $HOME\.codeograph\cache\telemetry\run-*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $HOME\.codeograph\cache\telemetry\run-<run-id>.jsonl -Wait -Tail 10
```

Each line is one LLM call attempt. Look at `"status"` (`success`/`error`), `"error_class"`
(`LlmRateLimitExhausted` means it retried and gave up; `LlmSchemaValidationError` is a different,
unrelated failure — see §6.3), and `"total_latency_ms"` (a call reporting several hundred thousand
milliseconds genuinely spent that long retrying, it isn't stuck). If the log is growing — even
slowly — the process is working, not hung.

### 6.2 `PackagePrefixGrouping produced only 1 domain group from N rendered classes`

This warning is expected, not an error, for any corpus where all classes live directly under one
package with no further sub-packages (a small/flat example corpus is a common case). Auto-grouping
by package prefix has nothing to split on in that shape, so everything renders into a single
`misc` domain module. If you want real per-domain grouping for a flat-package corpus, configure
`ManualMappingGrouping` via `[render.typescript.domain_mapping]` in your config instead of relying
on auto-detection.

### 6.3 A render logs `WARNING ... Failed to render class '...'` but the run still finishes

Per-class render failures are isolated by design (ADR-008 D-008-2) — one bad class is skipped and
logged, it does not abort the rest of the group or the run. The most common cause is
`LlmSchemaValidationError` from the model wrapping its output in markdown code fences (```` ``` ````)
or otherwise not honoring the "raw output only" instruction, despite the render prompt explicitly
asking for structured JSON output. This is a model-compliance issue, not a Codeograph bug — some
models are simply less reliable at forced structured/tool-calling output than others, especially
through third-party API aggregators. If a specific class keeps failing:
- Re-run `render` again — this is a per-call model behavior, not deterministic, and the same class
  often succeeds on a second attempt.
- Try a different model/provider for the same corpus and compare — reliability varies noticeably
  between models even within the same price tier.
- Don't assume the failure is fatal to the whole render: check the "Wrote N file(s)" summary line
  and the actual output directory before concluding anything is broken.

### 6.4 Pre-flight cost estimate says "unavailable"

This means `CODEOGRAPH_LLM_MODEL` (and resolved provider label) don't match any row in
`codeograph/llm/prices.toml` — most often because the model id string doesn't exactly match what
the provider actually expects (see §1.3's warning about fictional/guessed model ids). The run isn't
blocked by this — it's a degraded estimate, not an error — but it's worth double-checking the model
id against the provider's own docs before proceeding, since the same mismatch that breaks the price
lookup can also mean the real API call fails or resolves to an unexpected model.

---

## 7. Non-interactive / CI use

Both the confirmation gate and any prompt-driven flow need a real TTY. In CI or any non-interactive
context:
- `--non-interactive` — auto-aborts the confirmation gate instead of hanging on a prompt.
- `--yes` / `-y` — pre-confirms, so the run proceeds past the threshold without a prompt.

Use `--non-interactive` alone for "never spend without a human present"; add `--yes` only once
you've decided a given automated run is allowed to proceed unattended.
