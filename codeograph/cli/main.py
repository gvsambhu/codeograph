import click

from codeograph import __version__


@click.group()
@click.version_option(version=__version__, prog_name="codeograph")
def cli() -> None:
    """Ingest a Java/Spring Boot codebase; emit a knowledge graph and migration scaffold."""


@cli.command()
@click.argument("input_path", metavar="INPUT")
@click.option(
    "--out",
    required=True,
    metavar="DIR",
    help="Output directory. Must not exist or must be empty unless --force is used.",
)
@click.option(
    "--ast-only",
    is_flag=True,
    default=False,
    help="Parse and emit the graph only; skip LLM enrichment passes.",
)
def run(input_path: str, out: str, ast_only: bool) -> None:
    """Run the Codeograph pipeline on INPUT.

    INPUT may be a local directory path, a git URL, or a path to a .zip archive.
    """
    # TODO (M3): load Settings from config
    # TODO (M4): acquire input via InputAcquisition
    # TODO (M6): parse Java sources via Parser → ClassFacts
    # TODO (M7): score complexity via ComplexityScorer → extend ClassFacts
    # TODO (M8): build and write graph via GraphWriter → out/graph.json + out/manifest.json
    raise NotImplementedError("run command not yet implemented")
