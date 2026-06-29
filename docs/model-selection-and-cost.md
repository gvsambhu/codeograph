# Model Selection & Cost

> Prices were captured **2026-06-26** (see the dated price table in §6) and move frequently — treat
> every figure as an **estimate, not a quote; verify before relying.** This file is also the **data
> source for the ADR-027 pre-flight cost estimate**: the price table here is what the cost-safety
> floor reads, so keep it dated and in sync with the machine-readable price source.

---

## 1. What the LLM actually does here (sets the bar)

Codeograph's LLM job is **per-class semantic extraction with structured output** (Pass 1) plus one
corpus **synthesis** call (Pass 2). It is **code comprehension + reliable JSON**, *not* agentic code
generation. The gating capability is **structured-output reliability**, not raw coding skill — size
the model for *that*.

Two consequences:

* The benchmark figures quoted below are **agentic-coding** scores (SWE-Bench etc.). That task is
  **harder** than Codeograph's comprehension+JSON task, so a model that does respectably there
  "comfortably clears the bar" here. Read the numbers as a conservative floor.
* **Caching is cost-only — it never changes output.** Its absence is never a capability blocker; it
  only affects price.

---

## 2. Sizing tiers

| Purpose | Dense floor | MoE floor | Output quality |
|---|---|---|---|
| Smoke / wiring | ~3–4B (Phi-3.5 Mini 3.8B, ~2.4 GB Q4) | n/a | parseable JSON, crude |
| Basic validation | ~7–8B (Qwen2.5-Coder 7B, Llama 3.3 8B) | ~30B-tot/3B-act (Qwen3-30B-A3B) | coherent, mostly-right |
| Decent / serious | ~30B+ dense → frontier | Qwen3-235B-A22B class | trustworthy |

> **MoE-for-local trap.** A Mixture-of-Experts model cuts *active* params (so it decodes fast) but
> you still hold **all** experts in RAM (Qwen3-30B-A3B ≈ 18 GB Q4). For **local** runs, prefer a
> **small dense** model over an MoE of the same "active" size.

---

## 3. Local vs cloud / free vs paid

| Tier | Local? | Free API? | Notes |
|---|---|---|---|
| Phi-3.5 3.8B / Qwen2.5-Coder 7B / Llama 3.3 8B | ✅ (2.4–8 GB, 16 GB RAM/CPU) | self-host | the local story; no key |
| Qwen3-30B-A3B (MoE) | ⚠️ ~24 GB RAM/GPU | — | fast active, heavy to hold |
| **Gemini 2.5/3 Flash** | ❌ | ✅ **best free** — ~1,500 req/day, 1M TPM, no card, native structured output, its own caching | recommended free first-run |
| Groq (Llama 3.3 70B) | ❌ | ✅ ~1,000 RPD (reduced 2026) | fast bursts |
| Mistral (Experiment tier) | ❌ | ✅ ~1B tok/mo **but opt-in to data training** | privacy caveat |
| DeepSeek / Qwen via API | weights local-able | ❌ free dev API gone Apr 2026 (trial only) | cheap paid below |

---

## 4. Open-weight cloud models (cheap-serious tier)

Open-weight models served via a cloud API — large enough to need a host, but with published weights
(so the model can be re-hosted elsewhere). Mistral Large and the Qwen line sit in the same family as
the entries below.

| Model | Arch | Ctx | API in/out | Cache? | License | Reported |
|---|---|---|---|---|---|---|
| DeepSeek V4-Pro | MoE | 1M | **$0.28 / $2.48** | yes | open | 80.6% SWE-Bench Verified; "Opus-class, 10× cheaper output" |
| MiniMax M3 | MoE (sparse, ~15× faster decode) | 1M | **$0.60 / $0.60** | — | open | tops open-weight SWE-Bench Pro 59.0% |
| Kimi K2.7-Code (Moonshot) | ~1T / 32B-act MoE | 256K | $0.95 / $4.00 (**$0.19 cache-hit**) | yes | Mod. MIT | leads open weights ~54 AA-index |
| GLM-5.2 (Zhipu / Z.ai) | 744B / 40B-act MoE | 1M | $1.40 / $4.40 (**$0.26 cached-in**) | yes | MIT | beats GPT-5.5 long-horizon @ ~1/6 cost |
| Qwen3.6 Plus / Qwen3-Coder | dense + MoE | long | $0.01–$1.25 in | varies | Apache | small variants run local |
| Mistral Large 3 (open-weight) | multimodal flagship | 262K | **$0.50 / $1.50** | — | Apache 2.0 | open-weight flagship; current Mistral Large line |

> **Two caveats this section must carry.**
> 1. **Open weights ≠ runs locally.** At 744B–1T params these are a **cloud-API** tier, not a local
>    option.
> 2. **Data jurisdiction.** Each model's first-party endpoint is hosted in a specific jurisdiction,
>    and some cheap tiers require opt-in training on your data — check both before sending
>    proprietary source. **Mitigation enabled by open weights:** run the *same* model via a host in
>    your preferred jurisdiction (Together / Fireworks / OpenRouter / Bedrock) to decouple model
>    choice from API jurisdiction. Recommended for sensitive code.

---

## 5. Serious / default tier (cloud, paid)

| Model | API in / out |
|---|---|
| **Claude Sonnet 4.6** (v1 default pin) | **$3 / $15** |
| Claude Haiku 4.5 | $1 / $5 |
| Gemini 3.1 Pro | $2 / $12 |
| Gemini 3 Flash | $0.50 / $3 |

---

## 6. Dated price table (ADR-027 estimate data source)

> **Captured 2026-06-26. Prices move monthly — verify before relying. This is the table the ADR-027
> pre-flight estimator reads; the figure it shows is an estimate, not a quote.**

| Model | Provider note | Input $/M tok | Output $/M tok | Cache-hit input $/M | Notes |
|---|---|---|---|---|---|
| Claude Sonnet 4.6 | Anthropic (v1 default) | 3.00 | 15.00 | ~0.30 (cached read) | structured-output reliable |
| Claude Haiku 4.5 | Anthropic | 1.00 | 5.00 | ~0.10 | cheaper Claude |
| Gemini 3.1 Pro | Google | 2.00 | 12.00 | native cache | |
| Gemini 3 Flash | Google | 0.50 | 3.00 | native cache | |
| Gemini 2.5/3 Flash (free) | Google free tier | 0.00 | 0.00 | native cache | ~1,500 req/day, 1M TPM |
| DeepSeek V4-Pro | first-party / re-hosted | 0.28 | 2.48 | yes | jurisdiction caveat §4 |
| MiniMax M3 | first-party / re-hosted | 0.60 | 0.60 | — | |
| Kimi K2.7-Code | Moonshot | 0.95 | 4.00 | 0.19 | |
| GLM-5.2 | Zhipu / Z.ai | 1.40 | 4.40 | 0.26 cached-in | |
| Qwen3.6 Plus / Qwen3-Coder | varies | 0.01–1.25 | varies | varies | small variants local |
| Mistral Large 3 | Mistral (open-weight) | 0.50 | 1.50 | — | Apache 2.0; 262K ctx |
| Local (Phi-3.5 / Qwen2.5-Coder 7B / Llama 3.3 8B) | self-host | 0.00 | 0.00 | n/a | hardware cost only |

> **Refresh & source-of-truth.** Prices drift — typically downward, roughly monthly. The single
> source of truth for prices is a **machine-readable file** (format = learner's choice, e.g.
> `prices.toml`); this human table is kept in sync with it, and the ADR-027 pre-flight estimator
> reads the structured file — **never this prose table**. Re-verify on a **quarterly cadence** (and
> on any provider price-change announcement) and bump the capture date above when you do. The
> **project maintainer** owns this refresh. External price *accuracy* cannot be CI-gated (it is
> inherently manual), but doc-vs-source *parity* can be (the ADR-014 prompt-freshness / ADR-023
> pin-parity gate pattern).

---

## 7. Cost reality (≈300-class service, prefix-cache on)

Scales **linearly** with class count. A 25-class sample service is **cents** even on Sonnet.

| Model | Est. cost for ~300 classes |
|---|---|
| Gemini free tier / local | **$0** |
| MiniMax M3 | ~$0.50 |
| DeepSeek V4-Pro | ~$0.55 |
| Gemini 3 Flash | ~$0.80 |
| GLM-5.2 | ~$1 |
| Kimi K2.7 | ~$1.3 |
| Claude Haiku 4.5 | ~$1.5 |
| **Claude Sonnet 4.6** | **~$3–5** |

> State these plainly. The adoption barrier is **perception** of cost, not the actual figure — a
> typical small service is cheap even on the priciest tier.

---

## 8. Recommendation ladder (by user intent)

> `TODO(learner)` — this section is the **opinionated POV**; write it in your own voice. The skeleton
> below is the factual scaffold; the "why I'd pick this" framing is yours.

1. **Free first-run** → Gemini Flash free tier.
2. **No-cloud / privacy** → small dense local (Qwen2.5-Coder 7B / Phi-3.5).
3. **Cheap-serious** → MiniMax M3 / DeepSeek V4-Pro (re-hosted in your preferred jurisdiction for sensitive source, §4).
4. **Production default** → Sonnet 4.6 / Gemini 3.1 Pro.

---

## 9. Caching note

OpenRouter **supports** prompt caching (do not claim otherwise):

* **Automatic** for DeepSeek / OpenAI / Gemini 2.5 (zero config).
* **Pass-through** `cache_control` for Anthropic / Alibaba-Qwen (forward the breakpoint).
* It does **sticky routing** to maximize cache hits.
* Genuinely absent only on **free `:free` routes** and on explicit-cache providers when the client
  library forgets to forward the breakpoint (a verify-in-CI item — ADR-005's payload-snapshot test
  catches it).

ADR-005 §6's "`cache_control` must stay reachable" is satisfiable via OpenRouter.

---

## 10. Relationship to ADRs

* **ADR-005** (token utilization) — single-model v1, prefix caching; this doc is the cost companion.
* **ADR-013 / ADR-001** (provider abstraction + credentials) — the provider expansion that makes the
  cheap/free tiers above reachable in v1 (Gemini-direct, Groq, DeepSeek-direct via the generalized
  OpenAI-compatible provider).
* **ADR-027** (temporary cost-safety floor) — consumes §6's dated price table for its pre-flight
  estimate.
* **ADR-016** (cost-control CLI, v1.1) — dollar-accurate budgeting; supersedes ADR-027 at `1.1.0`.
