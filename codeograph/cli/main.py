"""CLI entry point for Codeograph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from codeograph import __version__
from codeograph.cli.cache import cache_cli
from codeograph.cli.eval import eval_cli
from codeograph.cli.render import render_cli
from codeograph.logging_config import configure_logging

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def _resolve_log_level(
    log_level: str | None,
    verbose: int,
    quiet: int,
) -> str:
    """Resolve the effective console log level from --log-level / -v / -q.

    Precedence (most specific wins):

    * ``--log-level X`` — explicit value; wins over any flag.
    * ``-v`` (count) — DEBUG. Counts greater than 1 are accepted but collapse
      to DEBUG (no V=INFO/D=DEBUG ladder; the kickoff locks -v → DEBUG).
    * ``-q`` (count) — 1× = WARNING, 2× = ERROR. Higher counts clamp to
      ERROR (no FATAL level in stdlib).
    * default — INFO.

    ``-v`` and ``-q`` together is a usage error. ``-v`` together with
    ``--log-level`` is allowed (the explicit value wins); the user
    typo'd themselves if they specified both, but the resolution is
    deterministic.
    """
    if log_level is not None and (verbose or quiet):
        # Explicit level trumps flag heuristics, but raise a warning so
        # the user notices the conflict.
        click.echo(
            f"--log-level overrides -v/-q (using {log_level!r}; -v={verbose}, -q={quiet} ignored)",
            err=True,
        )
    if log_level is not None:
        return log_level.upper()
    if verbose and quiet:
        raise click.UsageError("Cannot specify both -v and -q")
    if verbose:
        return "DEBUG"
    if quiet == 1:
        return "WARNING"
    if quiet >= 2:
        return "ERROR"
    return "INFO"


@click.group()
@click.version_option(version=__version__, prog_name="codeograph")
@click.option(
    "--log-level",
    default=None,
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    help=(
        "Console log level. Mutually exclusive with -v/-q in spirit but "
        "--log-level wins on conflict (with a warning to stderr). "
        "Default: INFO."
    ),
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Set console log level to DEBUG.",
)
@click.option(
    "-q",
    "--quiet",
    count=True,
    help="Set console log level to WARNING (-q) or ERROR (-qq).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    log_level: str | None,
    verbose: int,
    quiet: int,
) -> None:
    """Ingest a Java/Spring Boot codebase; emit a knowledge graph and migration scaffold."""
    resolved = _resolve_log_level(log_level=log_level, verbose=verbose, quiet=quiet)
    # Initial configure_logging with out_dir=None installs the console
    # handler only. Subcommands that have an --out option (currently
    # only `run`) re-call configure_logging with the resolved out_dir
    # to attach the JSONL file handler. configure_logging is idempotent
    # and rebuilds the config from scratch each call.
    configure_logging(console_level=resolved, out_dir=None)
    # Stash for subcommands that need to re-configure with their own
    # out_dir, or that want to log via RunIdLoggerAdapter.
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = resolved


cli.add_command(cache_cli)
cli.add_command(eval_cli)
cli.add_command(render_cli)


def _prepare_output_directory(out: str, force: bool) -> Path:
    """Handles output directory resolution and safety validation (FR-27)."""
    out_dir = Path(out).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_dir}' already exists and is non-empty. Use --force to overwrite."
            )
    return out_dir


def _load_settings() -> Settings:
    """Instantiates Settings and translates Pydantic ValidationErrors into Click UsageErrors.

    Uses dynamic metadata-driven env var resolution (validation_alias) to avoid hardcoding specific provider keys.
    """
    from pydantic import ValidationError, AliasChoices
    from codeograph.config.settings import Settings

    try:
        return Settings()
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            loc = error.get("loc")
            field_name = str(loc[0]) if loc else "unknown"

            # Resolve the environment variable dynamically using settings metadata
            field_info = Settings.model_fields.get(field_name)
            if field_info and field_info.validation_alias:
                alias = field_info.validation_alias
                if isinstance(alias, AliasChoices):
                    # Use the first choice (preferred bare key)
                    env_var = alias.choices[0]
                elif isinstance(alias, str):
                    env_var = alias
                else:
                    env_var = str(alias)
            else:
                env_var = f"CODEOGRAPH_{field_name.upper()}"

            msg = error.get("msg", "Validation error")
            if msg.startswith("Value error, "):
                msg = msg[len("Value error, ") :]
            errors.append(f"- {env_var}: {msg}")
        err_msg = "Invalid configuration:\n" + "\n".join(errors)
        raise click.UsageError(err_msg) from exc

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
@click.option(
    "--eval",
    "run_eval",
    is_flag=True,
    default=False,
    help="Run evaluation automatically after generation completes.",
)
@click.pass_context
def run(
    ctx: click.Context,
    input_path: str,
    out: str,
    ast_only: bool,
    force: bool,
    run_eval: bool,
) -> None:
    """Run the Codeograph pipeline on INPUT.

    INPUT may be a local directory path, a git URL, or a path to a .zip archive.

    The manifest is written **exactly once** at a terminal checkpoint, per
    the ADR-025 terminal-write protocol amendment (see
    ``codeograph.manifest.assembler``). The pipeline collects all run-state
    fragments (graph, optional llm-annotations, optional cache_stats, optional
    scorecards) and hands them to the assembler for a single build; strict-on-
    write Pydantic validation is the boundary check.
    """
    # --- Output directory resolution + safety (FR-27) --------------------
    out_dir = _prepare_output_directory(out, force)

    # --- Logging re-configuration with the resolved out_dir --------------
    log_level = ctx.obj.get("log_level", "INFO")
    configure_logging(console_level=log_level, out_dir=out_dir)

    # --- Lazy imports (keep CLI startup fast) ----------------------------
    from codeograph.analyzer.corpus_analyzer import CorpusAnalyzer
    from codeograph.config.settings import Settings
    from codeograph.graph.graph_assembler import GraphAssembler
    from codeograph.graph.graph_builder import GraphBuilder
    from codeograph.graph.graph_writer import GraphWriter
    from codeograph.input.acquirers.base_acquirer import AcquisitionError
    from codeograph.input.input_acquirer import InputAcquirer
    from codeograph.manifest import ManifestAssembler
    from codeograph.manifest.artefact import GraphArtefact
    from codeograph.manifest.run_id import generate_run_id
    from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
    from codeograph.parser.java_file_parser import JavaFileParser
    from codeograph.parser.regex_fallback import RegexFallback

    # --- Per-run data (generated once, threaded into the assembler) ------
    run_id = generate_run_id()
    settings = _load_settings()

    acquirer = InputAcquirer()
    corpus = None

    try:
        click.echo(f"Acquiring input: {input_path}")
        try:
            corpus = acquirer.acquire(input_path)
        except AcquisitionError as exc:
            raise click.ClickException(str(exc)) from exc

        total_files = sum(len(m.java_files) for m in corpus.modules)
        click.echo(f"Discovered {len(corpus.modules)} module(s), {total_files} Java file(s).")

        corpus_id = corpus.modules[0].name if corpus.modules else "default-corpus"

        analyzer = CorpusAnalyzer(
            dispatcher=FileParserDispatcher(
                java_parser=JavaFileParser(jar_path=settings.javaparser_jar),
                fallback=RegexFallback(),
            ),
            builder=GraphBuilder(),
            assembler=GraphAssembler(),
            writer=GraphWriter(),
        )

        # --- Pass 0: deterministic graph (graph_writer returns a GraphArtefact).
        graph_artefact: GraphArtefact = analyzer.analyze(corpus, out_dir)
        click.echo(f"Done Pass 0. Graph: {graph_artefact.path} (sha256={graph_artefact.sha256[:12]}…)")

        # --- LLM passes (full run only) ------------------------------------
        llm_annotations_artefact = None
        cache_stats = None

        if not ast_only:
            from codeograph.analyzer.llm_corpus_enricher import LlmCorpusEnricher
            from codeograph.llm.resolver import LlmProviderResolver
            from codeograph.telemetry.session_manager import TelemetrySessionManager
            from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator

            resolver = LlmProviderResolver(settings)
            telemetry_manager = TelemetrySessionManager(settings)
            stats_aggregator = TelemetryStatsAggregator()

            enricher = LlmCorpusEnricher(
                settings=settings,
                provider_resolver=resolver,
                telemetry_manager=telemetry_manager,
                stats_aggregator=stats_aggregator,
            )
            llm_annotations_artefact, cache_stats = enricher.enrich(
                corpus_id=corpus_id,
                graph_artefact=graph_artefact,
                out_dir=out_dir,
            )
        else:
            click.echo("AST-only mode requested. Skipping LLM passes.")

        # --- Eval (runs for both ast-only and full-LLM paths).
        scorecards = None
        if run_eval:
            from codeograph.evals.corpus_evaluator import evaluate_corpus

            evaluator = CorpusEvaluator()
            scorecards = evaluator.evaluate(out_dir)

        # --- Terminal manifest write ----------------------------------------
        assembler = ManifestAssembler()
        manifest = assembler.assemble(
            run_id=run_id,
            codeograph_version=__version__,
            source_path=str(corpus.corpus_root.resolve()),
            corpus_id=corpus_id,
            llm_skipped=ast_only,
            graph_artefact=graph_artefact,
            llm_annotations_artefact=llm_annotations_artefact,
            cache_stats=cache_stats,
            scorecards=scorecards,
            compile_checks=None,
        )
        manifest_path = assembler.write_to(manifest, out_dir)
        click.echo(f"Done. Manifest: {manifest_path}")

    finally:
        if corpus is not None:
            acquirer.cleanup(corpus)

