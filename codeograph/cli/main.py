"""CLI entry point for Codeograph."""

from __future__ import annotations

import sys
from pathlib import Path

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
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite output directory if it already exists and is non-empty.",
)
def run(input_path: str, out: str, ast_only: bool, force: bool) -> None:
    """Run the Codeograph pipeline on INPUT.

    INPUT may be a local directory path, a git URL, or a path to a .zip archive.
    """
    # Resolve output directory and enforce output-path safety (FR-27).
    out_dir = Path(out).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_dir}' already exists and is non-empty. "
                "Use --force to overwrite."
            )

    # Lazy imports keep startup fast and isolate heavy dependencies from the
    # CLI layer — only loaded when `run` is actually invoked.
    from codeograph.analyzer.corpus_analyzer import CorpusAnalyzer
    from codeograph.graph.graph_assembler import GraphAssembler
    from codeograph.graph.graph_builder import GraphBuilder
    from codeograph.graph.graph_writer import GraphWriter
    from codeograph.input.acquirers.base_acquirer import AcquisitionError
    from codeograph.input.input_acquirer import InputAcquirer
    from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
    from codeograph.parser.java_file_parser import JavaFileParser
    from codeograph.parser.regex_fallback import RegexFallback

    acquirer = InputAcquirer()
    corpus = None

    try:
        click.echo(f"Acquiring input: {input_path}")
        try:
            corpus = acquirer.acquire(input_path)
        except AcquisitionError as exc:
            raise click.ClickException(str(exc)) from exc

        total_files = sum(len(m.java_files) for m in corpus.modules)
        click.echo(
            f"Discovered {len(corpus.modules)} module(s), {total_files} Java file(s)."
        )

        analyzer = CorpusAnalyzer(
            dispatcher=FileParserDispatcher(
                java_parser=JavaFileParser(),
                fallback=RegexFallback(),
            ),
            builder=GraphBuilder(),
            assembler=GraphAssembler(),
            writer=GraphWriter(),
        )

        manifest_path = analyzer.analyze(corpus, out_dir)
        click.echo(f"Done. Manifest: {manifest_path}")

    finally:
        if corpus is not None:
            acquirer.cleanup(corpus)
