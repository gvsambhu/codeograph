"""``codeograph render`` subcommand (ADR-008 Fork 6, Q2 decoupling decision).

Reads an existing manifest.json output directory produced by ``codeograph run``
and renders a TypeScript/NestJS project from the graph + LLM annotations.

Rendering is intentionally decoupled from LLM execution so that:
  - Rendering parameters (ORM, policies, budget) can be tuned without
    re-running the expensive LLM annotation passes.
  - CI can cache annotation artefacts and re-render cheaply on prompt change.

Usage::

    codeograph render --from ./run-output --out ./ts-out --target typescript

The subcommand is registered in ``cli/main.py`` via ``cli.add_command(render_cli)``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath

import click

__all__ = ["render_cli"]


# ---------------------------------------------------------------------------
# --list-targets eager callback (must be defined before the decorator uses it)
# ---------------------------------------------------------------------------


def _list_targets_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Print registered targets and exit when --list-targets is passed."""
    if not value or ctx.resilient_parsing:
        return
    # Trigger self-registration of concrete renderer packages.
    import codeograph.renderers.typescript_nestjs  # noqa: F401
    from codeograph.renderers import RendererRegistry

    targets = RendererRegistry.targets()
    if targets:
        click.echo("Registered renderer targets:")
        for t in targets:
            click.echo(f"  {t}")
    else:
        click.echo("No renderer targets registered.")
    ctx.exit()


# ---------------------------------------------------------------------------
# render subcommand
# ---------------------------------------------------------------------------


@click.command(name="render")
@click.option(
    "--from",
    "from_dir",
    required=True,
    metavar="DIR",
    type=click.Path(exists=True, file_okay=False, readable=True),
    help=(
        "Output directory from a previous 'codeograph run'.  "
        "Must contain graph.json, llm-annotations.json, and manifest.json."
    ),
)
@click.option(
    "--out",
    required=True,
    metavar="DIR",
    help="Destination directory for the rendered TypeScript project.",
)
@click.option(
    "--target",
    default="typescript",
    show_default=True,
    help="Renderer target.  Currently only 'typescript' is supported.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite --out if it already exists and is non-empty.",
)
@click.option(
    "--db-layer",
    default=None,
    help="Override TypeScriptConfig.db_layer (e.g. 'typeorm').",
)
@click.option(
    "--render-budget",
    default=None,
    type=int,
    help="Override TypeScriptConfig.render_budget (per-group class cap).",
)
@click.option(
    "--no-scaffold",
    is_flag=True,
    default=False,
    help="Skip emitting the NestJS scaffold files (package.json, tsconfig, etc.).",
)
@click.option(
    "--list-targets",
    is_flag=True,
    default=False,
    is_eager=True,
    expose_value=False,
    callback=_list_targets_callback,
    help="Print registered renderer targets and exit.",
)
def render_cli(
    from_dir: str,
    out: str,
    target: str,
    force: bool,
    db_layer: str | None,
    render_budget: int | None,
    no_scaffold: bool,
) -> None:
    """Render a TypeScript/NestJS project from an existing codeograph output.

    Reads graph.json and llm-annotations.json from FROM_DIR; writes the
    rendered TypeScript source to OUT (organised by domain module).
    """
    # Lazy imports keep CLI startup fast — only loaded when `render` is invoked.
    import datetime

    # Trigger self-registration of concrete renderer packages.
    import codeograph.renderers.typescript_nestjs  # noqa: F401
    from codeograph.config.settings import Settings
    from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph
    from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
    from codeograph.llm.factory import build_default_stack
    from codeograph.llm.middleware.retry_policy import RetryPolicy
    from codeograph.llm.prompts.loader import PromptLoader
    from codeograph.llm.providers.anthropic_provider import AnthropicProvider
    from codeograph.llm.types import CallContext, ProviderType, Purpose, Tier
    from codeograph.renderers import RendererRegistry
    from codeograph.telemetry.emitter import JsonlEmitter

    # --- validate input directory -----------------------------------------
    from_path = Path(from_dir).resolve()
    graph_path = from_path / "graph.json"
    annotations_path = from_path / "llm-annotations.json"

    for required in (graph_path, annotations_path):
        if not required.exists():
            raise click.UsageError(
                f"Required file not found: {required}. Run 'codeograph run' first to produce the artefacts."
            )

    # --- validate output directory ----------------------------------------
    out_path = Path(out).resolve()

    # Path-safety guard: refuse to clear a directory that contains or IS the cwd.
    _cwd = Path.cwd().resolve()
    if out_path == _cwd or _cwd.is_relative_to(out_path):
        raise click.UsageError(
            f"--out '{out_path}' is the current working directory or an ancestor of it. "
            "Choose a dedicated output directory to avoid accidental data loss."
        )

    if out_path.exists() and any(out_path.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_path}' already exists and is non-empty. Use --force to overwrite."
            )
        click.echo(f"Clearing existing files in {out_path} …")
        for child in out_path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    # --- load artefacts ---------------------------------------------------
    click.echo(f"Loading graph from {graph_path} …")
    with open(graph_path, encoding="utf-8") as fh:
        graph_dict = json.load(fh)

    graph = CodeographKnowledgeGraph.model_validate(graph_dict)

    click.echo(f"Loading annotations from {annotations_path} …")
    with open(annotations_path, encoding="utf-8") as fh:
        annotations: dict[str, object] = json.load(fh)

    # --- build renderer config from CLI overrides -------------------------
    raw_config: dict[str, object] = {}
    if db_layer is not None:
        raw_config["db_layer"] = db_layer
    if render_budget is not None:
        raw_config["render_budget"] = render_budget
    if no_scaffold:
        raw_config["include_scaffold"] = False

    # --- build LLM stack --------------------------------------------------
    settings = Settings()
    if not settings.anthropic_api_key:
        click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM render calls will fail unless mocked.")

    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_backend = SQLiteCacheBackend(settings.cache_dir / "cache.db")
    telemetry_dir = settings.cache_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    emitter_path = telemetry_dir / f"render-{target}-{run_ts}.jsonl"
    emitter = JsonlEmitter(emitter_path)

    tier_map = {
        Tier.FAST: settings.llm_model_fast or settings.llm_model,
        Tier.DEEP: settings.llm_model_deep or settings.llm_model,
        Tier.RENDER: settings.llm_model_render or settings.llm_model,
    }

    match settings.llm_provider:
        case ProviderType.ANTHROPIC:
            base_provider = AnthropicProvider(
                api_key=(settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""),
                tier_map=tier_map,
            )
        case _:
            raise click.ClickException(
                f"Provider '{settings.llm_provider}' is not supported by the render "
                f"subcommand in v1.  Use llm_provider=anthropic."
            )

    retry_policy = RetryPolicy()
    prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

    # Resolve the render prompt's content_hash_pin from the renderer's own prompt
    # directory so the cache key is tied to the actual prompt body (ADR-014/015).
    # The TypeScript renderer owns its prompts; the CLI must not hard-code the hash.
    _ts_render_prompts = PromptLoader(Path(__file__).parent.parent / "renderers" / "typescript_nestjs" / "prompts")
    _render_prompt = _ts_render_prompts.get("render_file", version="v1")
    _render_prompt_hash = _render_prompt.metadata.content_hash_pin

    render_ctx = CallContext(
        purpose=Purpose.RENDER,
        prompt_id="render_file",
        prompt_version="v1",
        prompt_content_hash=_render_prompt_hash,
        corpus_id=from_path.name,
        provider_name=settings.llm_provider,
    )
    provider = build_default_stack(base_provider, retry_policy, cache_backend, emitter, render_ctx)

    # --- instantiate renderer and run ------------------------------------
    click.echo(f"Building renderer for target '{target}' …")
    try:
        renderer = RendererRegistry.build(
            target=target,
            raw_config=raw_config,
            provider=provider,
            prompt_loader=prompt_loader,
            concurrency=settings.llm_concurrency,
        )
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("Rendering … (this will make LLM calls for each selected class)")
    file_map = renderer.render(graph, annotations)

    # Compile-checks sidecar (M4)
    import hashlib
    compile_checks = renderer.compile_checks()
    if compile_checks:
        sidecar_dict = {
            "schema_version": "1.0.0",
            "target": target,
            "renderer_version": "1.0.0", # Hardcoded for now
            "checks": [
                {
                    "name": c.name,
                    "cmd": c.cmd,
                    "workdir": str(c.workdir),
                    "required_tools": c.required_tools,
                    "pass_on_exit_codes": c.pass_on_exit_codes,
                }
                for c in compile_checks
            ]
        }
        sidecar_bytes = json.dumps(sidecar_dict, indent=2).encode("utf-8")
        sidecar_rel_path = PurePosixPath(f"evals/compile-checks.{target}.json")
        file_map[sidecar_rel_path] = sidecar_bytes
        
        # Manifest pointer update
        sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()
        manifest_path = from_path / "manifest.json"
        
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                manifest_dict = json.load(f)
            
            # Bump schema version
            manifest_dict["schema_version"] = "1.4.0"
            if "compile_checks" not in manifest_dict["artefacts"]:
                manifest_dict["artefacts"]["compile_checks"] = {}
            
            manifest_dict["artefacts"]["compile_checks"][target] = {
                "path": str(sidecar_rel_path),
                "schema_version": "1.0.0",
                "sha256": sidecar_sha256
            }
            
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_dict, f, indent=2)

    # --- PackagePrefixGrouping collapse warning (ADR-009 / Issue #7) --------
    # When no explicit domain_mapping was given, auto-grouping ran.  If it
    # collapsed all classes into a single group from a large class set, the
    # LCP is almost certainly too shallow (mixed-vendor packages).  Warn the
    # user and suggest ManualMappingGrouping as the escape hatch.
    if not raw_config.get("domain_mapping"):
        _domain_dirs = {
            p.parts[1]  # first segment after "src/"
            for p in file_map
            if len(p.parts) >= 3 and p.parts[0] == "src"
        }
        _src_ts_files = [
            p for p in file_map if p.parts[0] == "src" and p.name.endswith(".ts") and not p.name.endswith(".module.ts")
        ]
        if len(_domain_dirs) == 1 and len(_src_ts_files) > 5:
            click.echo(
                "WARNING: PackagePrefixGrouping produced only 1 domain group from "
                f"{len(_src_ts_files)} rendered classes. "
                "This usually means the longest common package prefix is too shallow "
                "(mixed-vendor codebase). "
                "Consider using ManualMappingGrouping via "
                "'[render.typescript.domain_mapping]' in your config. "
                "See ADR-009 Amendments for details.",
                err=True,
            )

    # --- write output files -----------------------------------------------
    out_path.mkdir(parents=True, exist_ok=True)
    written = 0
    for rel_path, content in file_map.items():
        dest = out_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        written += 1

    emitter.close()
    click.echo(f"Done. Wrote {written} file(s) to {out_path}.")
