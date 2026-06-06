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
    """
    # Resolve output directory and enforce output-path safety (FR-27).
    out_dir = Path(out).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_dir}' already exists and is non-empty. Use --force to overwrite."
            )

    # Re-configure logging with the resolved out_dir so logs.jsonl is
    # emitted into the same directory the run writes its other
    # artefacts to. The group callback installed the console handler
    # only; this call adds the JSONL file handler (idempotent rebuild).
    log_level = ctx.obj.get("log_level", "INFO")
    configure_logging(console_level=log_level, out_dir=out_dir)

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
        click.echo(f"Discovered {len(corpus.modules)} module(s), {total_files} Java file(s).")

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
        click.echo(f"Done Pass 0. Manifest: {manifest_path}")

        if ast_only:
            click.echo("AST-only mode requested. Skipping LLM passes.")
        else:
            import datetime
            import json

            from codeograph.config.settings import Settings
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

            settings = Settings()
            if not settings.anthropic_api_key:
                click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")

            # Setup Cache & Telemetry
            settings.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_backend = SQLiteCacheBackend(settings.cache_dir / "cache.db")
            telemetry_dir = settings.cache_dir / "telemetry"
            telemetry_dir.mkdir(parents=True, exist_ok=True)

            run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            corpus_id = corpus.modules[0].name if corpus.modules else "default-corpus"
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
            graph_path = out_dir / "graph.json"
            with open(graph_path, encoding="utf-8") as f:
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
            try:
                annotations = annotator.annotate(nodes)
            except Exception as e:
                click.echo(f"Pass 1 failed: {e}")
                raise

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
            try:
                # Pass 2 consumes Pass 1's in-memory annotations + the Pass 0 graph dict
                # (per CorpusSynthesizer.synthesize signature).
                synthesizer.synthesize(annotations, graph_data)
            except Exception as e:
                click.echo(f"Pass 2 failed: {e}")
                raise

            # Flush telemetry so the JSONL is readable for per-pass aggregation.
            emitter.close()

            # Update manifest.json: stamp llm_annotations sha256 + populate per-pass
            # cache_stats from the telemetry JSONL.  manifest schema_version is 1.1.0
            # (bumped in DC2); cache_stats is keyed by pass_1 / pass_2 per the schema.
            import hashlib

            from codeograph.graph.models.manifest_schema import CacheStats, CodeographRunManifest
            from codeograph.llm.types import Purpose

            try:
                # Load existing manifest via the pydantic model so writes round-trip
                # cleanly through the schema and reject any drift from contract.
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = CodeographRunManifest.model_validate_json(f.read())

                # Stamp llm-annotations sha256 (Pass 0 wrote sha256=None).
                annotations_path = out_dir / "llm-annotations.json"
                if annotations_path.exists():
                    with open(annotations_path, "rb") as bfh:
                        manifest.artefacts.llm_annotations.sha256 = hashlib.sha256(bfh.read()).hexdigest()

                # Aggregate telemetry JSONL by Purpose → pass label.  Each record is one
                # complete_structured call; cache_hit is True when CachingLlmProvider
                # short-circuited.  cost_usd_est is 0.0 in v1 (cost model deferred to v1.1
                # per ADR-016); saved_usd_est and incurred_usd_est therefore default to 0.0.
                purpose_to_pass = {Purpose.ANNOTATE.value: "pass_1", Purpose.SYNTHESIZE.value: "pass_2"}
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

                cache_stats: dict[str, CacheStats] = {}
                for pass_label, recs in per_pass.items():
                    if not recs:
                        continue
                    calls = len(recs)
                    hits = sum(1 for r in recs if r.get("cache_hit"))
                    hit_rate = (hits / calls) if calls else 0.0
                    incurred = sum(float(r.get("cost_usd_est", 0.0)) for r in recs if not r.get("cache_hit"))
                    saved = sum(float(r.get("cost_usd_est", 0.0)) for r in recs if r.get("cache_hit"))
                    cache_stats[pass_label] = CacheStats(
                        calls=calls,
                        hits=hits,
                        hit_rate=round(hit_rate, 4),
                        saved_usd_est=round(saved, 4),
                        incurred_usd_est=round(incurred, 4),
                    )

                if cache_stats:
                    manifest.cache_stats = cache_stats

                with open(manifest_path, "w", encoding="utf-8") as f:
                    f.write(manifest.model_dump_json(indent=2))

            except Exception as e:
                click.echo(f"Warning: Failed to update manifest.json: {e}")

            click.echo("LLM passes complete.")

        # --- Eval (runs for both ast-only and full-LLM paths) ---
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

                scorecards = runner.run(
                    output_dir=out_dir,
                    scorecard_kinds=kinds,
                )

                has_failure = any(any(c.result == "fail" for c in s.checks) for s in scorecards)

                if has_failure:
                    click.echo("Evaluation failed overall.")
                    sys.exit(1)
            except MissingOutputError as e:
                click.echo(f"Eval Error: {e}", err=True)
                sys.exit(2)

    finally:
        if corpus is not None:
            acquirer.cleanup(corpus)
