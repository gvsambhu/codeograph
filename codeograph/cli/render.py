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
from pathlib import Path

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

    render_ctx = CallContext(
        purpose=Purpose.RENDER,
        prompt_id="render_file",
        prompt_version="v1",
        prompt_content_hash="TODO",
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
