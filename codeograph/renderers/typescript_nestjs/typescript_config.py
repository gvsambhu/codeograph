"""TypeScriptConfig — Pydantic config class for the NestJS renderer (ADR-010).

Consumed by ``TypeScriptRenderer`` (M7) and validated by ``RendererRegistry.build()``
before the renderer is instantiated.  All fields have conservative defaults that
match the "happy path" for a standard Spring Boot → NestJS migration.

Field design follows the decisions recorded in the DC3 kickoff (2026-05-28):
    - db_layer: TypeORM (latest stable, pg driver) — Q1 answer
    - render_strategy: decouple rendering from LLM execution — Q2 answer
    - domain_mapping: manual opt-in, empty = PackagePrefixGrouping default — Q5 answer
    - db_adapter: pg — Q6 answer

ADR-010 Fork 9 policy fields (unsupported_feature_policy, security_feature_policy,
webflux_policy) control encounter-behaviour dispatch in the renderer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["TypeScriptConfig"]

# Literals for enum-style fields -----------------------------------------------

DbLayer = Literal["typeorm"]
"""v1 only supports TypeORM.  Extend to ``Literal["typeorm", "prisma"]`` in v1.1."""

DbAdapter = Literal["pg", "better-sqlite3"]
"""Node.js database driver.  ``"pg"`` is the production default (Q6)."""

UnsupportedFeaturePolicy = Literal["stub_todo", "silent_skip"]
"""Encounter-behaviour for Java features with no direct NestJS equivalent (ADR-010 Fork 9).

- ``stub_todo``: Emit valid TS with a greppable ``// TODO: Spring <FEATURE>`` stub (default).
- ``silent_skip``: Render the closest NestJS equivalent silently; no TODO comment.

Note: ``"refuse"`` was removed in the 2026-05-28 fixup round.  Unlike
``security_feature_policy`` and ``webflux_policy`` — which have concrete
class-level signals (@PreAuthorize, Mono<>/Flux<> return types) — there is
no robust deterministic detector for generic "unsupported Spring features"
at the class level.  ``stub_todo`` is the reviewable alternative.
See ADR-010 Amendments.
"""

SecurityFeaturePolicy = Literal["stub_todo", "silent_skip", "refuse"]
"""Encounter-behaviour for Spring Security annotations (@PreAuthorize, @Secured, etc.).

- ``stub_todo``: Emit endpoint WITHOUT auth + ``@UseGuards(/* TODO */)`` stub (insecure opt-in).
- ``silent_skip``: Render endpoint without auth and without any TODO (most permissive).
- ``refuse``: Skip the class entirely (default — prevents silently open endpoints).
"""

WebFluxPolicy = Literal["refuse", "translate_mono_only", "best_effort"]
"""Encounter-behaviour for Spring WebFlux reactive types (Mono<T>, Flux<T>).

- ``refuse``: Skip any class with reactive return types (default — avoids subtly broken output).
- ``translate_mono_only``: Translate ``Mono<T>`` → ``Promise<T>``; refuse classes with ``Flux<T>``.
- ``best_effort``: Translate ``Mono<T>`` → ``Promise<T>`` and ``Flux<T>`` → ``Observable<T>`` (RxJS).
"""

RenderStrategy = Literal["from_manifest"]
"""How the renderer acquires graph + annotations.

``"from_manifest"``: reads from an existing ``manifest.json`` in the output
directory.  This decouples rendering from LLM execution (Q2 decision).
"""


# Config class ------------------------------------------------------------------


class TypeScriptConfig(BaseModel):
    """Configuration for the TypeScript/NestJS renderer.

    All fields are optional with defaults.  Pass only the fields you need to
    override in ``[render.typescript]`` TOML config or via ``codeograph render``.
    """

    model_config = ConfigDict(extra="forbid")

    # -- Dependency / library choices ------------------------------------------

    db_layer: DbLayer = Field(
        default="typeorm",
        description=(
            "ORM layer to emit in the generated NestJS project.  "
            "v1 supports 'typeorm' only (NestJS ^10.4.0, TypeORM latest stable)."
        ),
    )

    db_adapter: DbAdapter = Field(
        default="pg",
        description=(
            "Node.js database driver package.  "
            "'pg' targets PostgreSQL (production default); "
            "'better-sqlite3' is available for local dev / CI."
        ),
    )

    # -- Rendering behaviour ---------------------------------------------------

    render_strategy: RenderStrategy = Field(
        default="from_manifest",
        description=(
            "How the renderer acquires graph + annotation data.  "
            "'from_manifest' reads from an existing manifest.json, "
            "decoupling rendering from LLM execution."
        ),
    )

    render_budget: int = Field(
        default=50,
        ge=1,
        le=500,
        description=(
            "Per-domain-group class budget cap fed to ClassSelector (ADR-009).  "
            "The three-tier selection ladder fires when a group exceeds this cap."
        ),
    )

    # -- Domain grouping -------------------------------------------------------

    domain_mapping: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Explicit {java_package_prefix: module_name} mapping for domain grouping.  "
            "Empty dict (default) activates PackagePrefixGrouping auto-detection.  "
            "Non-empty dict activates ManualMappingGrouping."
        ),
    )

    # -- Feature policies (ADR-010 Fork 9) -------------------------------------

    unsupported_feature_policy: UnsupportedFeaturePolicy = Field(
        default="stub_todo",
        description=(
            "Encounter-behaviour when the renderer meets a Java feature "
            "that has no direct NestJS equivalent.  "
            "'stub_todo' is the safe default (greppable TODO stubs)."
        ),
    )

    security_feature_policy: SecurityFeaturePolicy = Field(
        default="refuse",
        description=(
            "Encounter-behaviour for Spring Security annotations (@PreAuthorize, @Secured, etc.).  "
            "'refuse' is the default — prevents silently open endpoints."
        ),
    )

    webflux_policy: WebFluxPolicy = Field(
        default="refuse",
        description=(
            "Encounter-behaviour for Spring WebFlux reactive types "
            "(Mono<T>, Flux<T>).  "
            "'refuse' is the default — avoids subtly broken reactive translation."
        ),
    )

    # -- NestJS scaffold options -----------------------------------------------

    include_scaffold: bool = Field(
        default=True,
        description=(
            "When True, the renderer emits the full NestJS scaffold "
            "(main.ts, app.module.ts, package.json, tsconfig.json, etc.) "
            "in addition to the domain-module files."
        ),
    )

    strict: bool = Field(
        default=True,
        description=(
            'Emit ``"strict": true`` in the generated tsconfig.json.  Matches the project\'s TypeScript quality bar.'
        ),
    )
