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
    out_dir = Path(out).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_dir}' already exists and is non-empty. Use --force to overwrite."
            )

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
    from codeograph.manifest.schema import CacheStats, ScorecardPointer
    from codeograph.parser.file_parser_dispatcher import FileParserDispatcher
    from codeograph.parser.java_file_parser import JavaFileParser
    from codeograph.parser.regex_fallback import RegexFallback

    # --- Per-run data (generated once, threaded into the assembler) ------
    run_id = generate_run_id()
    settings = Settings()

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
        # The graph_writer never writes the manifest (per the ADR-025 amendment);
        # the assembler consumes the GraphArtefact at the terminal write.
        graph_artefact: GraphArtefact = analyzer.analyze(corpus, out_dir)
        click.echo(f"Done Pass 0. Graph: {graph_artefact.path} (sha256={graph_artefact.sha256[:12]}…)")

        # --- LLM passes (full run only) ------------------------------------
        llm_annotations_artefact: GraphArtefact | None = None
        cache_stats: dict[str, CacheStats] | None = None

        if not ast_only:
            import datetime
            import hashlib
            import json

            from codeograph.llm._prompts_generated import PromptId
            from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
            from codeograph.llm.factory import build_default_stack
            from codeograph.llm.middleware.retry_policy import RetryPolicy
            from codeograph.llm.prompts.loader import PromptLoader
            from codeograph.llm.providers.anthropic_provider import AnthropicProvider
            from codeograph.llm.types import CallContext, Purpose
            from codeograph.passes.pass1.annotator import NodeAnnotator
            from codeograph.passes.pass2.synthesizer import CorpusSynthesizer
            from codeograph.telemetry.emitter import JsonlEmitter

            if not settings.anthropic_api_key:
                click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")

            # Setup Cache & Telemetry
            settings.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_backend = SQLiteCacheBackend(settings.cache_dir / "cache.db")
            telemetry_dir = settings.cache_dir / "telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)

            run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            emitter_path = telemetry_dir / f"run-{corpus_id}-{run_ts}.jsonl"
            emitter = JsonlEmitter(emitter_path)

            # Base Provider — dispatches on settings.llm_provider
            from codeograph.llm.types import ProviderType, Tier

            def llm_tier_map(settings: Settings) -> dict[Tier, str]:
                return {
                    Tier.FAST: settings.llm_model_fast or settings.llm_model,
                    Tier.DEEP: settings.llm_model_deep or settings.llm_model,
                    Tier.RENDER: settings.llm_model_render or settings.llm_model,
                }

            tier_map = llm_tier_map(settings)

            match settings.llm_provider:
                case ProviderType.ANTHROPIC:
                    base_provider = AnthropicProvider(
                        api_key=settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else "",
                        tier_map=tier_map,
                    )
                case ProviderType.OLLAMA:
                    # OllamaProvider deferred to v1.1 per DC2 kickoff §"Open questions" #1.
                    raise NotImplementedError(
                        "Ollama provider is not implemented in v1. "
                        "Use llm_provider=anthropic; Ollama support is planned for v1.1."
                    )
                case ProviderType.BEDROCK:
                    # BedrockProvider deferred to v1.1 per DC2 kickoff §"Open questions" #1.
                    raise NotImplementedError(
                        "Bedrock provider is not implemented in v1. "
                        "Use llm_provider=anthropic; Bedrock support is planned for v1.1."
                    )
                case _:
                    raise ValueError(
                        f"Unknown llm_provider: {settings.llm_provider!r}. "
                        f"Must be one of: {[p.value for p in ProviderType]}."
                    )
            retry_policy = RetryPolicy()  # default policy
            prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

            # Load graph from Pass 0
            with open(graph_artefact.path, encoding="utf-8") as f:
                graph_data = json.load(f)
            nodes = graph_data.get("nodes", [])

            # --- Pass 1: Annotate Nodes ---
            click.echo("Running Pass 1 (Node Annotation)...")
            prompt_p1 = prompt_loader.get(PromptId.ANNOTATE_NODE)
            ctx_p1 = CallContext(
                purpose=Purpose.ANNOTATE,
                prompt_id=PromptId.ANNOTATE_NODE,
                prompt_version=prompt_p1.metadata.version,
                prompt_content_hash=prompt_p1.metadata.content_hash_pin,
                corpus_id=corpus_id,
                provider_name=settings.llm_provider,
            )
            provider_p1 = build_default_stack(base_provider, retry_policy, cache_backend, emitter, ctx_p1)
            annotator = NodeAnnotator(provider_p1, prompt_loader, out_dir, settings.llm_concurrency)
            annotations = annotator.annotate(nodes)

            # --- Pass 2: Synthesize Corpus ---
            click.echo("Running Pass 2 (Corpus Synthesis)...")
            prompt_p2 = prompt_loader.get(PromptId.SYNTHESIZE_CORPUS)
            ctx_p2 = CallContext(
                purpose=Purpose.SYNTHESIZE,
                prompt_id=PromptId.SYNTHESIZE_CORPUS,
                prompt_version=prompt_p2.metadata.version,
                prompt_content_hash=prompt_p2.metadata.content_hash_pin,
                corpus_id=corpus_id,
                provider_name=settings.llm_provider,
            )
            provider_p2 = build_default_stack(base_provider, retry_policy, cache_backend, emitter, ctx_p2)
            synthesizer = CorpusSynthesizer(provider_p2, prompt_loader, out_dir)
            # Pass 2 consumes Pass 1's in-memory annotations + the Pass 0 graph dict
            # (per CorpusSynthesizer.synthesize signature).
            synthesizer.synthesize(annotations, graph_data)

            # Flush telemetry so the JSONL is readable for per-pass aggregation.
            emitter.close()
            click.echo("LLM passes complete.")

            # --- Compute the llm-annotations artefact from the just-written file.
            # The assembler requires this when llm_skipped=False; an LLM pass
            # completing without producing the file is a producer bug.
            annotations_path = out_dir / "llm-annotations.json"
            if not annotations_path.exists():
                raise click.ClickException(
                    f"LLM passes completed but {annotations_path} was not produced. "
                    f"This is a producer bug; the manifest cannot be assembled "
                    f"without it (per ADR-025 §Invariants)."
                )
            llm_annotations_artefact = GraphArtefact(
                path=annotations_path,
                schema_version=graph_artefact.schema_version,  # same version as graph in v1
                sha256=hashlib.sha256(annotations_path.read_bytes()).hexdigest(),
            )

            # --- Aggregate cache_stats from telemetry.
            # 2.0.0 schema: only {calls, hits, hit_rate}; cost fields
            # (saved_usd_est / incurred_usd_est) deferred to a v1.1 minor
            # bump when a cost model lands (ADR-025 Fork 5).
            purpose_to_pass = {
                Purpose.ANNOTATE.value: "pass_1",
                Purpose.SYNTHESIZE.value: "pass_2",
            }
            per_pass: dict[str, list[dict[str, Any]]] = {"pass_1": [], "pass_2": []}
            if emitter_path.exists():
                with open(emitter_path, encoding="utf-8") as tf:
                    for line in tf:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
                        pass_label = purpose_to_pass.get(rec.get("purpose"))
                        if pass_label:
                            per_pass[pass_label].append(rec)

            aggregated: dict[str, CacheStats] = {}
            for pass_label, recs in per_pass.items():
                if not recs:
                    continue
                calls = len(recs)
                hits = sum(1 for r in recs if r.get("cache_hit"))
                hit_rate = round((hits / calls) if calls else 0.0, 4)
                aggregated[pass_label] = CacheStats(
                    calls=calls,
                    hits=hits,
                    hit_rate=hit_rate,
                )
            if aggregated:
                cache_stats = aggregated
        else:
            click.echo("AST-only mode requested. Skipping LLM passes.")

        # --- Eval (runs for both ast-only and full-LLM paths).
        # Eval runs BEFORE the manifest write so the scorecards can be
        # included in the single terminal manifest write. Standalone
        # `codeograph eval` (B6) reads+adds+writes the manifest separately.
        scorecards: dict[str, ScorecardPointer] | None = None
        if run_eval:
            click.echo("Running evaluation (--eval requested)...")
            import sys

            from codeograph.evals.runner import EvalRunner, MissingOutputError

            try:
                runner = EvalRunner()
                kinds = ["graph"]
                for child in out_dir.iterdir():
                    if child.is_dir() and child.name not in ("evals", ".codeograph"):
                        kinds.append(child.name)
                scorecard_models = runner.run(
                    output_dir=out_dir,
                    scorecard_kinds=kinds,
                )

                # Build ScorecardPointer dict from the written scorecard files
                # so the assembler has the (path, sha256, overall) tuple per kind.
                import hashlib  # local import keeps the no-LLM-pass path slim

                scorecards = {}
                for sc in scorecard_models:
                    sc_filename = "graph-scorecard.json" if sc.kind == "graph" else f"{sc.kind}-scorecard.json"
                    sc_path = out_dir / "evals" / sc_filename
                    if sc_path.exists():
                        sc_sha = hashlib.sha256(sc_path.read_bytes()).hexdigest()
                    else:
                        # EvalRunner should always have written the file; this
                        # is defensive against a future refactor mistake.
                        sc_sha = "0" * 64
                    overall = "pass" if all(c.result in ("pass", "skip") for c in sc.checks) else "fail"
                    scorecards[sc.kind] = ScorecardPointer(
                        path=f"evals/{sc_filename}",
                        sha256=sc_sha,
                        overall=overall,
                    )

                has_failure = any(c.result == "fail" for sc in scorecard_models for c in sc.checks)
                if has_failure:
                    click.echo("Evaluation failed overall.")
                    sys.exit(1)
            except MissingOutputError as e:
                click.echo(f"Eval Error: {e}", err=True)
                sys.exit(2)

        # --- Terminal manifest write ----------------------------------------
        # Per the ADR-025 terminal-write protocol: the manifest is written
        # exactly once per command, at this terminal checkpoint. Every
        # referenced file is final, every sha256 is computable, the
        # §Invariants hold. No intermediate manifest ever exists on disk.
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
            compile_checks=None,  # render command adds these in B5
        )
        manifest_path = assembler.write_to(manifest, out_dir)
        click.echo(f"Done. Manifest: {manifest_path}")

    finally:
        if corpus is not None:
            acquirer.cleanup(corpus)
