# Requirements

The functional and non-functional requirements codeograph is built against. Architecture decisions
that implement them are recorded as ADRs under [`docs/adr/`](adr/README.md), and each ADR cites the
requirements it satisfies — so traceability runs from a decision back to its requirement, not the
other way round. Requirements here state *what* the system must do; they do not name the designs
that chose *how*.

**Release markers.** Every requirement carries `[v1]` or `[v1.1]`.

| Marker | Meaning |
|---|---|
| `[v1]` | Shipped in v1 |
| `[v1.1]` | Planned for v1.1 — paths and flags named in these requirements do not exist yet |

Identifiers are stable and are never reused. A retired requirement keeps its number so existing
references continue to resolve.

---

## Functional

### Core pipeline

- **FR-1** `[v1]` — Accept any Java/Spring Boot project directory as input (Gradle or Maven).
- **FR-2** `[v1]` — Extract a structured knowledge graph (JSON) from the source, independent of any
  render target. Structure is extracted deterministically (FR-10); semantic enrichment is layered on
  top of it (FR-11).
- **FR-3** `[v1]` — Render the knowledge graph into idiomatic TypeScript/NestJS source.
- **FR-4** `[v1.1]` — Render the knowledge graph into idiomatic Go source — same graph, different
  target.
- **FR-5** `[v1]` — CLI accepts a `--target` flag to select the renderer.
- **FR-6** `[v1]` — All renderers implement a common `Renderer` interface; no target-specific code in
  the core pipeline.
- **FR-7** `[v1]` — Run code-quality evaluations per target (compile, coverage, LLM judge) and
  produce target-specific scorecards.
- **FR-7a** `[v1]` — Run graph-quality evaluations — structural completeness, relationship
  correctness, schema validity, internal consistency, semantic accuracy, reproducibility, and
  golden-graph agreement — and produce a graph scorecard.
- **FR-7b** `[v1]` — Maintain documented JSON Schema files for the knowledge graph under
  `codeograph/schema/*.schema.json` as the language-neutral source of truth. Every emitted graph
  validates against them: enforced at write time through the generated Pydantic models, and
  re-checked by the FR-7a schema-validity evaluation.
- **FR-7c** `[v1]` — The deterministic graph (`graph.json`) is regression-tested against committed
  golden files under `tests/golden/<corpus>/` for the project's test corpora — a hand-built
  edge-case fixture and a pinned real Spring project. CI diffs every run byte-equal in canonical
  form. Golden refreshes are deliberate (`--update-goldens`), and each refresh records its diff
  category: update-golden, fix-bug, or intentional-change. The committed example run (FR-9) ships
  its `graph.json` as illustrative output, not as a byte-equal regression golden.
- **FR-8** `[v1]` — Support provider switching by environment variable. The v1 provider set is
  `anthropic | openrouter | openai_compatible`; `ollama` and `bedrock` are `[v1.1]`. The
  `openai_compatible` provider reaches any API-key, OpenAI-compatible endpoint through a
  configurable base URL, with no coded vendor allowlist; `openrouter` is its OpenRouter-URL preset.
  All providers accept any model id as free-form pass-through — no project-blessed allowlist.
- **FR-9** `[v1]` — Include at least one complete example run per target, with committed output and
  evaluation scorecards.
- **FR-10** `[v1]` — Structural and syntactic facts — classes, methods, annotations, imports,
  dependencies — are extracted deterministically from the source, not by an LLM.
- **FR-11** `[v1]` — Semantic facts — service intent, domain boundaries, migration hints — are
  extracted by an LLM operating on the deterministic output.
- **FR-12** `[v1]` — The complexity scorecard uses named industry-standard metrics with numeric
  thresholds. No subjective high/medium/low buckets.
- **FR-13** `[v1]` — CLI accepts `--max-classes-per-domain N` (default 3) to cap rendering output
  per domain, bounding token spend and keeping runs reproducible. A value of `0` disables the cap.
- **FR-14** `[v1]` — When the cap is reached, rendering selects classes deterministically, ordered by
  a documented rule, so runs are reproducible. The knowledge graph always covers every class — only
  rendering is capped.

### Quality infrastructure

- **FR-15** `[v1]` — All prompts live as versioned files under `codeograph/prompts/`; scorecards
  record the prompt filenames and versions used.
- **FR-16** `[v1]` — Every LLM call emits telemetry: `run_id`, provider, model, prompt file, prompt
  version, input and output tokens, cost estimate, latency, and timestamp. Per-call records are
  written to a sidecar JSONL; aggregate statistics roll into the run manifest. `run_id` is the
  correlation key joining manifest, logs, and telemetry.
- **FR-17** `[v1]` — LLM responses are cached content-addressed on provider, model, prompt version,
  rendered prompt, and input hash. Cache hits are recorded in telemetry.
- **FR-18** `[v1]` — Every scorecard records exact model version strings, not family names.
- **FR-19** `[v1]` — A `pytest` suite at `tests/` covers unit and integration tests. CI blocks merge
  on failure; unit-test coverage target is 80% or above.
- **FR-20** `[v1]` — Every tool invocation writes a run manifest (`manifest.json`) and structured
  logs (`logs.jsonl`) into the output directory, alongside the run's other artefacts.
- **FR-21** `[v1]` — Secret scanning runs in CI on every push and pull request; merges are blocked on
  detection.
- **FR-27** `[v1]` — Output-path safety: all run artefacts are written inside the output directory;
  an output directory that is the working directory, or an ancestor of it, is rejected; a non-empty
  output directory is never silently overwritten — `--force` is required.

### Quality hardening

- **FR-22** `[v1.1]` — CLI supports cost estimation before a run (`--dry-run`) and a hard spend
  ceiling (`--max-cost-usd`). *v1 ships an interim mechanism instead: call and token ceilings with a
  confirmation gate (`--max-llm-calls`, `--max-tokens-total`, `--llm-call-confirm-threshold`).*
- **FR-23** `[v1.1]` — Snapshot tests lock byte-stable rendered output for a fixed input and cached
  responses; unexplained drift fails CI.
- **FR-24** `[v1.1]` — Negative tests assert graceful failure with specific error messages for at
  least six malformed-input classes. The baseline classes:
  1. **Zip bomb** — extracted size exceeds the configured cap; abort with a size-limit error before
     extraction completes.
  2. **Zip path traversal** — an archive entry resolves outside the extraction root; reject the
     archive.
  3. **Corrupt or malformed archive** — input is not a readable archive; return a clear error.
  4. **Acquisition failure** — the source cannot be fetched, or the URL is unreachable or
     credential-gated; return an actionable error naming the cause.
  5. **Empty corpus** — no `.java` files remain in scope after discovery; fail loudly with a
     user-readable message and a non-zero exit, never an empty-graph pass-through.
  6. **No recognised build file** — neither a Maven nor a Gradle build file is present; reject the
     corpus with a clear error rather than recording an unknown build system.
- **FR-25** `[v1.1]` — An LLM-judge calibration suite discriminates known-good from known-bad output
  at documented thresholds, committed as a calibration record.
- **FR-26** `[v1.1]` — Prompt-injection mitigation: source is wrapped in data tags with explicit
  instruction guards, escaped for prompt-breaking sequences, and validated by a negative test.
- **FR-28** `[v1.1]` — A determinism contract documents per-field determinism classification for the
  graph schema.

---

## Non-functional

- **NFR-1** — **Retired.** No longer tracked as a requirement. The number is retained so existing
  references resolve.
- **NFR-2** `[v1]` — A defined token-utilization strategy governs LLM input construction; v1 ships
  prefix caching. `[v1.1]` A token and cost scorecard surfaces spend per run.
- **NFR-3** `[v1]` — Evaluation results are reproducible: seed, model version, and prompt version are
  tracked per target.
- **NFR-4** `[v1]` — CI runs lint, unit tests, and the TypeScript evaluation path on every push.
  `[v1.1]` The Go evaluation path lands with the Go renderer.
- **NFR-5** `[v1]` — Adding a new target language requires no changes to the analyzer or the core
  pipeline — only a new renderer, a compile-check entry, and renderer-authoring documentation. v1
  ships a short "adding a renderer" section in `CONTRIBUTING.md`. `[v1.1]` The full renderer guide
  lands with the second renderer, which is what makes the pattern real.

---

## Revision history

These requirements were first drafted before implementation began, and were revised during design
review as decisions sharpened or rescoped them. **This section closes at this document's first
commit** — from that point, the git history of this file is the record of change.

| Date | Requirement | Change | Driver |
|---|---|---|---|
| 2026-06-14 | FR-24 | "6+ malformed-input classes" enumerated as six named classes with required failure behaviours | design review; ADR-002 |
| 2026-06-19 | FR-8 | Provider set replaced — `anthropic \| ollama \| bedrock` became `anthropic \| openrouter \| openai_compatible`; `ollama` and `bedrock` moved to v1.1 | design review; ADR-013 |
| 2026-06-19 | FR-16 | `run_id` added to the telemetry payload as the manifest-to-logs correlation key; per-call records routed to a sidecar JSONL with aggregates in the run manifest | design review; ADR-015, ADR-022 |
| 2026-06-19 | FR-22 | Deferred to v1.1. v1 ships call and token ceilings with a confirmation gate in place of cost estimation and a spend ceiling | design review; ADR-027 |
| 2026-06-19 | NFR-2 | Token and cost scorecard deferred to v1.1. v1 commits graph scorecards and ships prefix caching | design review |
| 2026-06-19 | NFR-5 | Full renderer guide deferred to v1.1; v1 ships a short `CONTRIBUTING.md` section. The guide waits on a second renderer to make the pattern real | design review; ADR-008 |
| 2026-06-29 | FR-8 | Generalised — the OpenAI-compatible provider accepts any base URL, with no vendor allowlist | design review; ADR-013 |
| 2026-08-05 | NFR-1 | Retired. Number retained so existing references resolve | — |

Three requirements moved from v1 to v1.1 during design review — FR-22, NFR-2 and NFR-5. In each case
v1 ships a narrower capability that meets the immediate need, and the fuller form is scheduled.
