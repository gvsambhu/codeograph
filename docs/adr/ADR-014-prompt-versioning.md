---
status: accepted
date: 2026-05-17
deciders: learner
consulted: AI design advisor
informed: future contributors
---

# ADR-014 — Prompt Versioning

## Context and Problem Statement

Codeograph's LLM pipeline runs prompts for three distinct purposes — per-node annotation (Pass 1), corpus synthesis (Pass 2), target-language rendering (Pass 3). Each purpose has at least one prompt; prompts evolve over time as wording is tuned, schemas tightened, or framework-idiom references refined. The legacy implementation embedded prompts as inline Python f-strings inside `extractor.py` and per-language writer classes; there was no version field, no separate prompt files, no Anthropic `cache_control` annotation, and no way for an evaluator to compare "Pass 1 with prompt v2" against "Pass 1 with prompt v3" in the same run.

ADR-014 makes prompts first-class artefacts. Prompts live as Markdown files with YAML frontmatter under `codeograph/prompts/`; each version is a distinct file; a per-prompt alias file marks the production default; identifiers (`prompt_id`, `prompt_version`, `prompt_content_hash`) thread through ADR-013's `CallContext` into ADR-015's cache key and telemetry records. A required `content_hash_pin` in the frontmatter catches the legacy "edit-in-place silently invalidates cache" bug at pre-commit time.

The scope is narrow: this ADR defines where prompts live, how they're versioned, what templating engine renders them, how multiple versions coexist, how variable contracts are validated, and how code references prompts. Prompt content (the actual words) is implementation detail; eval / regression of prompt quality is owned by ADR-017.

## Decision Drivers

* **Prompts as artefacts, not code.** Treat prompts as first-class deliverables, not strings buried in Python files.
* **Silent-edit defense.** The legacy domain-keyed cache silently served stale results after prompt changes; the new scheme must catch in-place edits at pre-commit / load time, before they reach production.
* **Eval reproducibility (ADR-007).** Goldens recorded against a specific prompt version must remain re-runnable after newer versions land.
* **A/B testing.** Multiple versions live in the same run when comparing prompt candidates.
* **Cacheable-prefix declaration (ADR-005 §6 + ADR-013 Fork 7).** Prompts declare which segments are cacheable; provider translates to native `cache_control`.
* **Templating safety.** Prompts embed Java source and JSON examples — the templating engine must not collide with `{`/`}` characters.
* **Auditable default promotion.** Moving from v2 to v3 as production default must appear as a deliberate PR diff, not an implicit "latest" lookup.
* **PR-reviewable prompts.** Prompt changes render readably in GitHub diff; non-code reviewers can edit Markdown files.
* **Type-safe call sites.** Code references prompts by autocompletable constant, not by raw string.

## Considered Options

Each fork below was evaluated against the drivers. Options that were considered and rejected appear in the Pros and Cons section at the end.

### Fork 1 — Storage location

* (a) Inline Python constants in code.
* **(b) Markdown files with YAML frontmatter in `codeograph/prompts/`. ✅**
* (c) Structured YAML/JSON files in `codeograph/prompts/`.
* (d) External prompt registry (LangSmith / Langfuse / etc.).
* (e) Hybrid — code constants for short prompts, files for long.

### Fork 2 — Versioning scheme

* (a) Semver (`v1.0.0`, `v1.1.0`).
* (b) Simple integer (`v1`, `v2`).
* (c) Content hash only.
* (d) Date-based (`2026-05-16`).
* **(e) Hybrid — human label + content hash; `content_hash_pin` **required** in frontmatter. ✅**

### Fork 3 — Templating engine

* (a) Python f-strings.
* (b) `str.format` / `format_map`.
* **(c) Jinja2 with custom delimiters (`<<var>>`, `<% block %>`, `<# comment #>`); `StrictUndefined`. ✅**
* (d) Mustache / Handlebars.
* (e) `string.Template` (`$var`).
* (f) Custom regex.

### Fork 4 — Multi-version coexistence

* (a) Only latest live; old versions in git history.
* (b) All versions live; code references default = latest.
* (c) All versions live; code MUST reference specific version.
* **(d) All versions live; alias file `default.yaml` marks default. ✅**

### Fork 5 — Validation (required-variables)

* (a) Declarative in frontmatter.
* (b) Inferred from template body.
* **(c) Declarative + verified — frontmatter `required_vars` + `optional_vars`, cross-checked against Jinja body parse at load time. ✅**
* (d) No declaration; runtime `StrictUndefined` catches missing.

### Fork 6 — Identification at call site

* (a) Bare string literals.
* (b) Hand-maintained `PromptId` enum.
* **(c) Generated constants module via pre-commit hook. ✅**
* (d) Typed handle classes per prompt.

## Decision Outcome

### Fork 1 — Storage: (b) Markdown with YAML frontmatter

Layout:

```
codeograph/prompts/
├── annotate_node/
│   ├── default.yaml            ← alias file (Fork 4)
│   ├── v1.md
│   ├── v2.md
│   └── v3.md
├── synthesize_corpus/
│   ├── default.yaml
│   └── v1.md
└── render_file/
    ├── default.yaml
    └── v1.md
```

Each `vN.md` file has YAML frontmatter followed by a Jinja2 template body with `# System` / `# User` section markers:

```markdown
---
id: annotate_node
version: v3
purpose: ANNOTATE
required_vars: [node_id, graph_context, source_body]
optional_vars: [neighbors]
cacheable_segments: [system, schema]
content_hash_pin: 7b2a8e3d
---

# System
You are a senior Java/Spring Boot reviewer. Given the node and its source,
return a NodeAnnotation matching the schema...

# User
Node ID: <<node_id>>

Graph context:
<<graph_context>>

Source:
<<source_body>>

<% if neighbors %>
Neighbors:
<% for n in neighbors %>
- <<n.id>>: <<n.kind>>
<% endfor %>
<% endif %>
```

`PromptLoader` reads the file, parses the frontmatter into a Pydantic `PromptMetadata` model, validates `content_hash_pin`, runs Fork 5 validation, splits the body into `system` and `user` segments, and returns a `Prompt` object cached in memory after first load.

Prompts ship with the wheel via `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"codeograph/prompts" = "codeograph/prompts"
```

### Fork 2 — Versioning: (e) Hybrid label + content hash; pin REQUIRED

The version label is the integer suffix in the filename (`v1`, `v2`, `v3`). The content hash is `sha256(normalized_body)[:8]` computed at load time. Both appear in the `Prompt` object; both are used:

* Label is used in references, telemetry, eval pins, and cache key.
* Content hash is used in cache key (silent-edit defense) and verified against `content_hash_pin` in frontmatter.

```python
@dataclass(frozen=True)
class Prompt:
    id: str              # "annotate_node"
    version: str         # "v3"
    metadata: PromptMetadata
    system: str          # rendered system segment
    user: str            # rendered user segment template (Jinja2 source pre-render)
    content_hash: str    # sha256(normalized_body)[:8]
```

**`content_hash_pin` is REQUIRED.** PromptLoader fails to load any prompt file whose frontmatter omits `content_hash_pin` or whose recomputed hash doesn't match. The pre-commit hook `scripts/update_prompt_hash_pins.py` recomputes the hash for each staged `.md` file under `codeograph/prompts/` and updates the pin in the frontmatter; CI re-runs the hook and fails on diff.

**Normalization** for hashing: trim trailing whitespace per line, normalize line endings to `\n`, single trailing newline. Frontmatter is *not* included in the hash (only the body); this lets us bump `content_hash_pin` without recursively affecting the hash.

**Default label scheme is integer** (`v1`, `v2`, `v3`). The label is a string field; if a prompt ever needs semver granularity, `v3.1.0` is allowed. Don't impose semver discipline before it's needed.

### Fork 3 — Templating: (c) Jinja2 with custom delimiters

```python
# codeograph/llm/prompts/renderer.py
from jinja2 import Environment, StrictUndefined

_ENV = Environment(
    variable_start_string="<<",
    variable_end_string=">>",
    block_start_string="<%",
    block_end_string="%>",
    comment_start_string="<#",
    comment_end_string="#>",
    keep_trailing_newline=True,
    undefined=StrictUndefined,   # missing var raises immediately
    autoescape=False,            # prompts are not HTML
)

def render(template_source: str, **vars: object) -> str:
    return _ENV.from_string(template_source).render(**vars)
```

Custom delimiters chosen because prompt bodies routinely embed Java source (`Map<String, List<Foo>>`) and JSON examples (`{"key": "value"}`); curly-brace delimiters would force escape discipline that the legacy review identified as fragile.

`StrictUndefined` enforces the "no silent failures" stance — missing variable raises `UndefinedError` at render time with a clear message, rather than producing an empty string.

Convention documented in `CONTRIBUTING.md`:
* Variable substitution — `<<var>>`
* Blocks — `<% if %>`, `<% for %>`, `<% endif %>`, `<% endfor %>`
* Comments — `<# ... #>`
* All other Jinja2 features (filters, inheritance, macros) work as documented.

### Fork 4 — Multi-version: (d) Alias file marks default

Each prompt directory has a `default.yaml`:

```yaml
# codeograph/prompts/annotate_node/default.yaml
default: v3

# Optional future fields:
# staging: v4-rc1     ← canary candidate
# deprecated: [v1]    ← versions slated for removal
```

`PromptLoader` resolution:

```python
prompt = loader.get("annotate_node")              # reads default.yaml → v3
prompt = loader.get("annotate_node", version="v2") # pinned, ignores alias
```

Promoting v3 → v4 as default is a deliberate `default.yaml` edit, surfacing as a one-line diff in the PR. No code change required; eval pins remain valid; old versions stay loadable.

The alias mechanism extends naturally to future canary / staged rollout policies without re-designing the file format.

### Fork 5 — Validation: (c) Declarative + verified

Frontmatter declares the variable contract:

```yaml
required_vars: [node_id, graph_context, source_body]
optional_vars: [neighbors]
```

At load time, `PromptLoader` uses `jinja2.meta.find_undeclared_variables` to extract every variable referenced in the body. Cross-check:

* Every variable in `required_vars` MUST appear in the body. Unused declared → load error.
* Every variable in the body MUST appear in `required_vars` or `optional_vars`. Undeclared in body → load error.
* Loop-local variables (e.g. `n` in `<% for n in neighbors %>`) are excluded from the cross-check via Jinja2's AST visit.

```python
class PromptValidationError(Exception): pass

def _validate(prompt: Prompt) -> None:
    body_vars = _extract_jinja_vars(prompt.user) | _extract_jinja_vars(prompt.system)
    declared = set(prompt.metadata.required_vars) | set(prompt.metadata.optional_vars)
    missing_in_declaration = body_vars - declared
    unused_declarations = set(prompt.metadata.required_vars) - body_vars
    if missing_in_declaration or unused_declarations:
        raise PromptValidationError(
            f"Prompt {prompt.id} v{prompt.version}: "
            f"undeclared body vars: {missing_in_declaration}; "
            f"declared-but-unused required vars: {unused_declarations}"
        )
```

Failure at load time (process startup or first prompt access) — surfaces drift early, not mid-pipeline at the 247th Pass 1 call.

### Fork 6 — Identification at call site: (c) Generated constants module

A pre-commit hook generates `codeograph/llm/_prompts_generated.py` from the filesystem:

```python
# codeograph/llm/_prompts_generated.py
"""Auto-generated by scripts/gen_prompt_constants.py — do not edit."""

class PromptId:
    """Constants for every prompt in codeograph/prompts/."""
    ANNOTATE_NODE = "annotate_node"
    SYNTHESIZE_CORPUS = "synthesize_corpus"
    RENDER_FILE = "render_file"
```

Re-exported via `codeograph/llm/__init__.py`:

```python
from codeograph.llm._prompts_generated import PromptId  # noqa: F401
```

Call sites use the constant:

```python
from codeograph.llm import PromptId
prompt = loader.get(PromptId.ANNOTATE_NODE)
```

Pre-commit hook (`scripts/gen_prompt_constants.py`) walks `codeograph/prompts/`, builds the class body, writes the file, stages it. CI re-runs the hook and fails on diff (`git diff --exit-code codeograph/llm/_prompts_generated.py`).

This gives autocomplete + dead-reference detection (deleting a prompt directory removes the constant; references become `AttributeError` at import time) without manual drift between filesystem and code.

**`ruff format` and `mypy` are configured to ignore the generated file** via per-file selectors — the generator's output is canonical and shouldn't be re-formatted on save.

## Consequences

**Positive.**

* Prompts are first-class artefacts — GitHub renders them as documentation; non-code reviewers can edit `.md` files.
* Multi-version coexistence is structural — eval reproducibility and A/B testing both work without branch juggling.
* Silent-edit defense is enforced — required `content_hash_pin` + pre-commit verification catches in-place edits before they ship.
* Default promotion (v2 → v3) is a deliberate `default.yaml` PR diff; passive promotion via "latest" lookup is impossible.
* Jinja2 with custom delimiters handles embedded Java / JSON safely — no escaping discipline required.
* `StrictUndefined` matches the project's "no silent failures" philosophy.
* Required/optional variable contract is declared in frontmatter and cross-verified against the template body; drift caught at load time.
* Cacheable-segment declaration in frontmatter integrates with ADR-013's `CacheHint` translation cleanly.
* Generated `PromptId` constants give autocomplete + dead-reference detection without manual drift.
* Cache key composition (ADR-015) gets `prompt_version` + `prompt_content_hash` for free — every cached entry is content-addressed against the exact prompt version that produced it.
* Telemetry record (ADR-015) gets the same fields — every call's audit trail is linkable to the exact prompt that ran.

**Negative.**

* `PromptLoader` is ~80 LOC of new code; another ~30 LOC for validation; ~50 LOC for the pre-commit generator. Net ~160 LOC of new infrastructure.
* Two-place change for a new variable in a prompt — body and `required_vars`. Mitigated by load-time cross-check catching drift.
* Custom Jinja delimiters require a one-time `CONTRIBUTING.md` documentation step (per Confirmation §10); accepted in exchange for safe handling of embedded Java/JSON content.
* Pre-commit hash-pin mechanism is a workflow dependency; CI verification (per Confirmation §4) catches missing pin updates even if a local dev skips the hook.
* Generated constants file lives in git; small noise in `git log` when prompts are added or removed.
* Prompts ship with the wheel; install size increases marginally (~tens of KB).
* `default.yaml` alias indirection adds one file per prompt; small overhead.

## Confirmation

Confirmation that this decision is implemented correctly will come from:

1. **Directory layout exists** — `codeograph/prompts/<prompt_id>/{default.yaml, vN.md, ...}` populated for the three initial prompts (annotate_node, synthesize_corpus, render_file).
2. **`PromptLoader` operational** — loads all prompts at startup, validates frontmatter, computes and verifies `content_hash_pin`, runs Fork 5 cross-check.
3. **Pre-commit hook installed** — `.pre-commit-config.yaml` includes `update_prompt_hash_pins.py` and `gen_prompt_constants.py`; running pre-commit on a modified prompt file updates the pin and regenerates the constants file.
4. **CI gate** — workflow re-runs hooks and fails on `git diff` against committed `content_hash_pin` and `_prompts_generated.py`.
5. **`PromptId` class generated** — `codeograph/llm/_prompts_generated.py` exists, lists every prompt as a class attribute, re-exported via `codeograph/llm/__init__.py`.
6. **`render(...)` function** at `codeograph/llm/prompts/renderer.py` uses Jinja2 with custom delimiters and `StrictUndefined`.
7. **Validation error tested** — unit test confirms `PromptLoader` raises `PromptValidationError` on undeclared body vars and on unused declarations.
8. **Silent-edit defense tested** — unit test edits a prompt body without updating `content_hash_pin`, confirms loader raises.
9. **Multi-version coexistence tested** — unit test loads v2 explicitly while v3 is the default; both resolve correctly.
10. **`CONTRIBUTING.md` documents the prompt authoring conventions** — frontmatter fields, custom delimiter syntax, version-bump and pin-update workflow.

## Pros and Cons of the Considered Options

### Fork 1 — Storage location

**(a) Inline Python constants.**
* Good, because zero load mechanism — import and use.
* Good, because import-time type-checking.
* Bad, because prompts evolve as code changes; PR friction.
* Bad, because non-code reviewers can't edit comfortably.
* Bad, because templating is f-string only; cache_control structure buried.

**(b) Markdown with YAML frontmatter. ✅ Chosen.**
* Good, because prompts are first-class artefacts; GitHub renders them as documentation.
* Good, because cacheable structure declarative in frontmatter.
* Good, because templating engine choice independent of storage.
* Good, because multi-version coexistence is natural (file per version).
* Good, because banned-terms-style lint surface is a single directory.
* Bad, because runtime loading (~80 LOC PromptLoader); type-checking moves to load time.
* Bad, because two-file change for some semantic edits (body + frontmatter).

**(c) Structured YAML/JSON files.**
* Good, because all versions in one file.
* Good, because Pydantic validation at load time.
* Bad, because YAML for long multi-line strings is fiddly.
* Bad, because GitHub renders YAML as a code block, not as content.

**(d) External prompt registry.**
* Good, because built-in versioning, A/B testing, performance tracking.
* Bad, because external dep; offline/CI breaks; vendor lock-in.
* Bad, because eval reproducibility breaks (prompt could change server-side).

**(e) Hybrid (inline + files).**
* Good, because "right tool for the job" per prompt.
* Bad, because two storage mechanisms; inconsistent ergonomics; bad pattern at scale.

### Fork 2 — Versioning scheme

**(a) Semver.**
* Good, because familiar three-axis model.
* Bad, because judgment call every time — "patch or minor?"
* Bad, because doesn't catch silent edits.

**(b) Simple integer.**
* Good, because minimal cognitive load.
* Bad, because no semantic granularity.
* Bad, because doesn't catch silent edits.

**(c) Content hash only.**
* Good, because silent-edit catastrophe impossible.
* Bad, because unreadable in PR review.
* Bad, because no chronology; no human discoverability.

**(d) Date-based.**
* Good, because chronological ordering trivial.
* Bad, because collisions on a busy day.
* Bad, because doesn't catch silent edits.

**(e) Hybrid — label + content hash, pin REQUIRED. ✅ Chosen.**
* Good, because silent-edit detection via content hash.
* Good, because human-readable references and PR diffs via label.
* Good, because cache key automatic — caller doesn't compute hashes.
* Good, because pre-commit hook auto-updates pin; CI verifies; drift impossible at workflow boundary.
* Good, because eval reproducibility automatic — golden test records `(id, version, content_hash)`.
* Bad, because two identifiers to track (small conceptual overhead).
* Bad, because pin mechanism requires pre-commit hook (workflow dependency).

### Fork 3 — Templating engine

**(a) f-strings.**
* Good, because stdlib.
* Bad, because not runtime-loadable from files.

**(b) `str.format`.**
* Good, because stdlib; works on loaded strings.
* Bad, because curly-brace collision with Java/JSON content is fatal.
* Bad, because no conditionals or loops.

**(c) Jinja2 with custom delimiters. ✅ Chosen.**
* Good, because curly-brace safe with custom delimiters; Java source flows verbatim.
* Good, because conditionals + loops + filters for future prompt evolution.
* Good, because `StrictUndefined` matches the project's "no silent failures" philosophy.
* Good, because mature, battle-tested (Flask, Ansible, Sphinx, dbt).
* Good, because no NIH risk.
* Bad, because new dep (~600 KB); team convention required for non-default delimiters.

**(d) Mustache / Handlebars.**
* Good, because logic-less simplicity.
* Bad, because no `StrictUndefined` equivalent — silent empty render is the legacy anti-pattern recurring.
* Bad, because Python ecosystem is small / unmaintained.

**(e) `string.Template`.**
* Good, because stdlib; `$var` syntax safe with curly braces.
* Bad, because no conditionals or loops.
* Bad, because templating migration is expensive when limits are hit.

**(f) Custom regex.**
* Good, because zero dep, total control.
* Bad, because NIH; every templating need becomes an added feature.
* Bad, because no editor / tooling support.

### Fork 4 — Multi-version coexistence

**(a) Only latest live.**
* Good, because single source of truth in working tree.
* Bad, because eval reproducibility broken; A/B testing impossible.

**(b) Latest is default.**
* Good, because default-is-latest happy path.
* Bad, because "latest" is implicit; promotions are passive (file appearing).
* Bad, because cache invalidation on every prompt PR for unpinned callers.

**(c) Must specify version.**
* Good, because every call site declares intent.
* Bad, because verbose; refactoring drag on rollout.
* Bad, because easy to leave call sites behind on promotion.

**(d) Alias file marks default. ✅ Chosen.**
* Good, because default-promotion auditable — `default.yaml` PR diff is the rollout signal.
* Good, because default-is-latest convenience preserved.
* Good, because future-friendly (canary / staging fields extend naturally).
* Good, because all versions live; eval and A/B testing both work.
* Bad, because one extra file per prompt (small overhead).
* Bad, because alias-version drift possible (loader validates at load time).

### Fork 5 — Validation (required vars)

**(a) Declarative only.**
* Good, because explicit contract.
* Bad, because manual sync risk — drift between body and declaration.

**(b) Inferred only.**
* Good, because zero authoring overhead.
* Bad, because implicit contract; no optional-var support.

**(c) Declarative + verified. ✅ Chosen.**
* Good, because explicit contract AND drift caught at load time.
* Good, because optional-var support.
* Good, because failure timing is early (load) not late (mid-pipeline).
* Bad, because more PromptLoader code (~25 LOC).

**(d) No declaration.**
* Good, because zero overhead.
* Bad, because no contract documentation; failure is mid-pipeline.

### Fork 6 — Identification at call site

**(a) Bare strings.**
* Good, because zero ceremony.
* Bad, because typos are runtime failures; no autocomplete; no refactor support.

**(b) Hand-maintained enum.**
* Good, because autocomplete; typos caught at type-check.
* Bad, because two-place change per new prompt (file + enum); drift possible.

**(c) Generated constants module. ✅ Chosen.**
* Good, because autocomplete + dead-reference detection without ongoing maintenance.
* Good, because filesystem is the authoritative source.
* Good, because pre-commit generation is committed; static analysis works without running anything.
* Bad, because generated file in git (small noise in `git log`).
* Bad, because formatter/linter must skip the generated file.

**(d) Typed handle classes.**
* Good, because autocomplete on render args; strongest type safety.
* Bad, because heavyweight (one class per prompt).
* Bad, because Jinja2 vs Python-typing impedance.
* Bad, because generation must maintain types in two places.

## More Information

**Relationships to other ADRs.**

* **ADR-005 §6** — cacheable-segment declaration in frontmatter feeds the `CacheHint` translation; together they implement the prompt-cache pass-through commitment.
* **ADR-007** — eval framework golden tests record `(prompt_id, prompt_version, prompt_content_hash)` and reload exactly that version on re-run. Fork 4's multi-version coexistence is what makes this reproducible.
* **ADR-013** — `CallContext` carries `prompt_id`, `prompt_version`, `prompt_content_hash` from this ADR's `Prompt` object through every wrapper in the middleware stack.
* **ADR-015** — cache key includes `prompt_id`, `prompt_version`, `prompt_content_hash`; telemetry records the same fields. Both depend on ADR-014's `Prompt` object as the source of truth.
* **ADR-017** (eval framework, v1.1) — prompt-quality regression tests will exercise the multi-version coexistence by pinning eval runs to specific versions for comparison.

**Deferred items.**

* **Content-policy lint framework** — `ContentPolicyRule` ABC with rules for URLs, banned-term patterns, etc. Not in v1; would be an additive amendment if a concrete need surfaces (e.g., client engagement, regulatory environment).
* **Canary / staged rollout** — `default.yaml` schema can grow `staging` and `percentage` fields for percentage-based routing. Not in v1; lands when first real canary need exists.
* **Prompt deprecation marking** — `default.yaml` `deprecated: [v1]` field for explicit "we plan to remove this." Not in v1; lands with first deprecation event.
* **Prompt change-log integration** — a `CHANGES.md` per prompt directory summarising version diffs in prose. Not in v1; lands when prompt count exceeds ~5 per purpose.

**Open questions for future review.**

The following questions should be revisited once concrete prompt-evolution experience has accumulated:
1. Did Jinja2's custom delimiters prove ergonomic, or did the convention create friction?
2. Did the pre-commit hash-pin update flow stay clean, or did contributors bypass it?
3. Did multi-version coexistence get exercised, or did the project always run the default?
4. Did `default.yaml` stay simple, or did it accumulate canary / staging / deprecation fields prematurely?
5. Did the generated `PromptId` constants prevent dead references, or did stale references leak through anyway?

**References.**

* MADR template — https://github.com/adr/madr
* Jinja2 — https://jinja.palletsprojects.com/
* Jinja2 custom delimiters — https://jinja.palletsprojects.com/en/stable/api/#jinja2.Environment
* Jinja2 `StrictUndefined` — https://jinja.palletsprojects.com/en/stable/api/#jinja2.StrictUndefined
* Jinja2 meta-introspection — https://jinja.palletsprojects.com/en/stable/api/#the-meta-api
* PEP 257 (docstrings as content-hash precedent) — https://peps.python.org/pep-0257/
* Pre-commit framework — https://pre-commit.com/
