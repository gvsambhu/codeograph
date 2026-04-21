---
status: "accepted"
date: 2026-04-21
decision-makers: Ganesh
consulted: —
informed: —
---

# ADR-001 — Project Skeleton & Configuration Strategy

## Context and Problem Statement

Codeograph is a CLI tool invoked by engineers against a local Java/Spring Boot project directory. Before any pipeline work can be built, three foundational decisions need to be locked: (1) the CLI framework, (2) the configuration hierarchy (how settings flow from defaults through a config file to runtime overrides), and (3) secrets handling (how API keys and provider credentials are supplied without ever being committed to source control). These choices shape every downstream module and must be made once, up front, before Stage 0 code lands.

Scope: the `codeograph` Python package skeleton, its entry point, and the single `Settings` object that all other modules will consume.

## Decision Drivers

* Must scale as subcommands and options grow (pipeline, eval, ops tracks each add flags)
* Typed validation of config at startup — misconfiguration should fail fast, not mid-run
* Secrets must never be committed; contributor onboarding should be self-documenting
* Minimise net new dependencies (Pydantic is already in the project for graph schema)
* Priority order of config sources (CLI > env > file > defaults) must be explicit and predictable
* Framework maturity — project expects external contributors, so decorator/API surface should be familiar

## Considered Options

**CLI framework**
* `argparse` (stdlib)
* `click`
* `typer`

**Configuration + secrets handling**
* Bundle A — `argparse` + manual 3-level YAML merge + `python-dotenv`
* Bundle B — `typer` + `pydantic-settings` (unified)
* Bundle C — `click` + manual 3-level YAML merge + `python-dotenv`
* Bundle D — `click` + `pydantic-settings` (unified)  ← code sketches in [adr-001-examples.md](adr-001-examples.md)

## Decision Outcome

Chosen: **`click` for the CLI, `pydantic-settings` for configuration, `.env` + OS env for secrets** (Bundle D).

* `click` is battle-tested, decorator-based, widely understood in the Python community, and handles the CLI surface this tool needs (single command with several options, room for future subcommands) cleanly. `argparse` scales poorly as options grow; `typer` is newer and couples tightly to type annotations.
* `pydantic-settings` gives a single typed `Settings` class with framework-managed priority (init kwargs > OS env > `.env` > `config.yaml` > field defaults). No custom merge code to maintain. Pydantic is already a project dependency.
* Secrets are loaded **only** from OS env / `.env`. `.env` is gitignored; `.env.example` is committed with placeholder values so contributors know what to set. `config.yaml` is committed and carries non-secret operational defaults (model names, caps, provider selection) — it must never contain secrets.

Priority order, highest to lowest:

```
CLI kwargs passed to Settings(**overrides)
  > OS environment variables
    > .env (local developer overrides, gitignored)
      > config.yaml (project-level non-secret defaults, committed)
        > field default values
```

### Consequences

* Good, because there is a single source of truth for configuration — no scattered `os.environ` calls across modules.
* Good, because typed fields catch misconfiguration at startup, not mid-run.
* Good, because net new dependencies are just `pydantic-settings` and `click`; no `python-dotenv`, no hand-rolled YAML merge.
* Good, because the `.env.example` pattern makes contributor onboarding self-documenting.
* Bad, because `pydantic-settings` YAML support requires ≥ 2.3 — must pin in `pyproject.toml`.
* Bad, because the priority order is framework-managed, so contributors must read the docs to understand it rather than trace merge code.
* Bad, because adding a new config field requires changes in two places (`Settings` class and, where applicable, `config.yaml`).

### Confirmation

* A unit test constructs `Settings(...)` under representative combinations (YAML only; YAML + env; YAML + env + init kwargs) and asserts the expected layer wins.
* CI runs `python -m codeograph --help` to confirm the CLI surface is intact on every PR.
* Pre-commit (or CI) rejects any `.env` committed to the repo; `.gitignore` excludes `.env`, `.env.local`, `.env.*.local`.

## Pros and Cons of the Options

### `argparse`

Standard library; no dependency. Imperative API.

* Good, because zero external dependency.
* Neutral, because every Python developer has seen it.
* Bad, because verbose and boilerplate-heavy as option count grows.
* Bad, because composing subcommand groups (pipeline / eval / ops) becomes unwieldy.

### `click`

Decorator-based; de facto standard for mid-sized Python CLIs.

* Good, because decorator surface keeps `main.py` short and readable.
* Good, because mature, stable API with large ecosystem (`click-plugins`, `click-completion`, etc.).
* Good, because subcommand groups (`@click.group`) compose cleanly for future expansion.
* Neutral, because it is an extra dependency — but a small, stable one.

### `typer`

Built on `click`; uses type annotations as the option spec.

* Good, because type-annotation-driven spec is concise.
* Bad, because newer and less established — fewer examples for contributors to lean on.
* Bad, because tight coupling to `Annotated[...]` metadata can surprise contributors unfamiliar with the pattern.

### Bundle A / C — manual 3-level YAML merge + `python-dotenv`

Explicit layers. Default dict → deep-merged YAML → CLI `dict.update`. Secrets read at call sites via `os.environ[...]`.

* Good, because the merge is code you can read end-to-end; no framework magic.
* Bad, because merge logic is hand-rolled and must be tested and maintained.
* Bad, because secrets accessed via `os.environ` scatter across modules; no single typed object.
* Bad, because adds `python-dotenv` as a dependency on top of the YAML parser.

### Bundle B — `typer` + `pydantic-settings`

Same config story as the chosen bundle, but `typer` CLI.

* Good, because inherits all `pydantic-settings` benefits.
* Bad, because carries the `typer`-specific cons above.

### Bundle D — `click` + `pydantic-settings`  *(chosen)*

One typed `Settings` object, one click entry point.

* Good, because the `Settings` priority order is framework-managed and well-documented upstream.
* Good, because CLI overrides are passed as `Settings(**kwargs)` — explicit and visible at the call site.
* Good, because `.env` loading is handled by `env_file=".env"` in `SettingsConfigDict`, no separate dotenv dependency.
* Bad, because YAML support requires `pydantic-settings ≥ 2.3`.

## More Information

Code sketches for all three CLI frameworks and all three config bundles live in [adr-001-examples.md](adr-001-examples.md) (scratch workspace, not committed to the repo).

Structural outcome — the two files this ADR commits the skeleton to:

```python
# codeograph/settings.py — canonical config object
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file="config.yaml",
        yaml_file_encoding="utf-8",
    )

    # Secrets — from .env or OS env only
    anthropic_api_key: str = Field(default="")
    ollama_base_url: str = Field(default="http://localhost:11434")
    aws_profile: str = Field(default="")

    # Pipeline config — from config.yaml, .env, or CLI override
    llm_provider: str = Field(default="anthropic")
    llm_model: str = Field(default="claude-sonnet-4-6")
    target: str = Field(default="ts")
    max_classes_per_domain: int = Field(default=3)

    # Extended by downstream ADRs:
    #   ADR-005 (token strategy) → batch_enabled, cache_enabled
    #   ADR-009 (rendering budget cap) → max_cost_usd
```

```python
# codeograph/main.py — CLI entry point
import click
from codeograph.settings import Settings

@click.command()
@click.argument("source")
@click.option("--target", type=click.Choice(["ts", "go"]), default=None)
@click.option("--max-classes-per-domain", type=int, default=None)
@click.option("--config", "config_path", default="config.yaml", show_default=True)
@click.option("--dry-run", is_flag=True, default=False)
def main(source, target, max_classes_per_domain, config_path, dry_run):
    overrides = {k: v for k, v in {
        "target": target,
        "max_classes_per_domain": max_classes_per_domain,
    }.items() if v is not None}
    settings = Settings(**overrides)
    # TODO: invoke pipeline
```

Deferred to later ADRs:
* `--dry-run` is wired now; the pipeline behaviour it triggers is defined in ADR-009 (rendering budget cap) and ADR-016 (cost-control CLI).
* `--max-cost-usd` lands with ADR-016; at that point both `main.py` and `Settings` gain the field.

Rejected alternative worth recording: 12-factor (env-only, no YAML). YAML is friendlier for local development; contributors shouldn't need to export ten env vars before a first run.

References:
* MADR template — https://github.com/adr/madr
* `pydantic-settings` docs — https://docs.pydantic.dev/latest/concepts/pydantic_settings/
* `click` docs — https://click.palletsprojects.com/
