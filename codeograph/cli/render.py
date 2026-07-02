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
    "--max-classes-per-domain",
    default=None,
    type=int,
    help="Override TypeScriptConfig.render_budget: max classes selected per domain group (FR-13).",
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
    max_classes_per_domain: int | None,
    no_scaffold: bool,
) -> None:
    """Render a TypeScript/NestJS project from an existing codeograph output.

    Reads graph.json and llm-annotations.json from FROM_DIR; writes the
    rendered TypeScript source to OUT (organised by domain module).
    """
    # Lazy imports keep CLI startup fast — only loaded when `render` is invoked.

    # Trigger self-registration of concrete renderer packages.
    import codeograph.renderers.typescript_nestjs  # noqa: F401
    from codeograph.cli.output_directory import prepare_output_directory
    from codeograph.cli.render_pipeline import RenderPipeline
    from codeograph.config.settings import Settings
    from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

    # --- validate input directory -----------------------------------------
    from_path = Path(from_dir).resolve()
    graph_path = from_path / "graph.json"
    annotations_path = from_path / "llm-annotations.json"

    for required in (graph_path, annotations_path):
        if not required.exists():
            raise click.UsageError(
                f"Required file not found: {required}. Run 'codeograph run' first to produce the artefacts."
            )

    # --- load artefacts (input boundary — stays in CLI handler) ----------
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
    if max_classes_per_domain is not None:
        raw_config["render_budget"] = max_classes_per_domain
    if no_scaffold:
        raw_config["include_scaffold"] = False

    # --- resolve output directory (clears on --force; cwd-safety guard) --
    out_path = prepare_output_directory(out, force, clear=True)

    # --- delegate to render pipeline -------------------------------------
    click.echo(f"Building renderer for target '{target}' …")
    settings = Settings()
    try:
        result = RenderPipeline(settings).run(
            graph=graph,
            annotations=annotations,
            raw_config=raw_config,
            target=target,
            from_path=from_path,
            out_path=out_path,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("Rendering … (this will make LLM calls for each selected class)")

    for warning in result.warnings:
        click.echo(warning, err=True)

    click.echo(f"Done. Wrote {result.written} file(s) to {out_path}.")
