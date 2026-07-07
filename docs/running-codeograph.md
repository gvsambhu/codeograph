# Running Codeograph — pipeline & command reference

This is the "what runs when, and in what order" reference. For **which model/provider to pick and
what it costs**, see [`docs/model-selection-and-cost.md`](model-selection-and-cost.md) instead —
this file is about the pipeline stages and CLI commands, not model choice.

---

## 1. The stages

| Stage | What it does | Command | Reads | Writes | Needs an LLM? |
|---|---|---|---|---|---|
| **Pass 0** — parse + graph build | AST parse of the corpus → deterministic graph | `codeograph run` (always runs) | source corpus | `graph.json`, `manifest.json` | No |
| **Pass 1** — per-class annotation | One LLM call per class: domain label, summary, migration hazards | `codeograph run` (skipped by `--ast-only`) | `graph.json` | `llm-annotations.json` | Yes |
| **Pass 2** — corpus synthesis | One LLM call: cross-domain synthesis over all Pass-1 output | same `run` invocation, same flag | Pass-1 output | folded into `llm-annotations.json` | Yes |
| **Render** | Translates selected classes into idiomatic target-language source (full logic, not skeletons) + a deterministic project scaffold | `codeograph render` (**separate command**) | a prior `run`'s `graph.json` + `llm-annotations.json` | target-language project (e.g. `.ts` files, `package.json`) | Yes — one call per selected class |
| **Eval** | Deterministic + code-quality scorecard checks against a run's output | `codeograph eval run` (or `run --eval`) | a run's output directory | `evals/*.json` scorecards | No |

**The one structural fact that matters:** `run` bundles Pass 0, and (unless `--ast-only`) Pass 1 +
Pass 2 together — there is no flag to do Pass 1 without Pass 2, or vice versa. `render` and `eval`
are always separate commands that read a *completed* `run` output directory; they cannot run first.

---

## 2. The order, if running back to back

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

## 3. Three scenarios — exact commands

### A. Smoke test — parse only, zero LLM calls, no API key needed

```powershell
python -m codeograph run <input> --out <dir> --ast-only
```
Confirms parsing + the JVM sidecar work. Check `manifest.json` for `"llm_skipped": true` and that
`graph.json` shows `extraction_mode: "ast"` (not `"regex_fallback"`).

### B. Full LLM run — Pass 0 + 1 + 2, no rendering, with the cost-safety net on

```powershell
python -m codeograph run <input> --out <dir> --max-llm-calls 40 --llm-call-confirm-threshold 1
```
`--llm-call-confirm-threshold 1` forces the pre-flight estimate + confirmation prompt on every run;
`--max-llm-calls` is a hard abort ceiling. Both are optional but recommended until you trust a given
provider/corpus combination. See `docs/model-selection-and-cost.md` for what these flags default to
and the full cost-safety-floor design (ADR-027).

### C. Everything back to back — parse → LLM → render → eval

```powershell
python -m codeograph run <input> --out <dir> --eval --max-llm-calls 40 --llm-call-confirm-threshold 1
python -m codeograph render --from <dir> --out <ts-dir> --target typescript
```
`--eval` folds evaluation into the `run` step itself — no separate `eval` invocation is needed unless
you want to re-check the same output later (`codeograph eval run <dir>`).

---

## 4. Re-running into the same output directory

`--force` on `run` **clears** the output directory first (so it always contains exactly one run's
artefacts) rather than merging into whatever is already there. The same applies to `render --force`.
Without `--force`, both commands refuse to write into a non-empty directory.

---

## 5. Non-interactive / CI use

Both the confirmation gate and any prompt-driven flow need a real TTY. In CI or any non-interactive
context:
- `--non-interactive` — auto-aborts the confirmation gate instead of hanging on a prompt.
- `--yes` / `-y` — pre-confirms, so the run proceeds past the threshold without a prompt.

Use `--non-interactive` alone for "never spend without a human present"; add `--yes` only once
you've decided a given automated run is allowed to proceed unattended.
