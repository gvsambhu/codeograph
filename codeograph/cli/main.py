"""CLI entry point for Codeograph."""

from __future__ import annotations

from pathlib import Path

import click

from codeograph import __version__


@click.group()
@click.version_option(version=__version__, prog_name="codeograph")
def cli() -> None:
    """Ingest a Java/Spring Boot codebase; emit a knowledge graph and migration scaffold."""
    pass

from codeograph.cli.cache import cache_cli
cli.add_command(cache_cli)

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
                f"Output directory '{out_dir}' already exists and is non-empty. Use --force to overwrite."
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
            return

        click.echo("Initializing LLM passes...")
        from codeograph.config.settings import Settings
        from codeograph.llm.providers.anthropic import AnthropicProvider
        from codeograph.llm.middleware.retry_policy import RetryPolicy
        from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
        from codeograph.telemetry.emitter import JsonlEmitter
        from codeograph.llm.factory import build_default_stack
        from codeograph.llm.types import CallContext, Purpose
        from codeograph.llm.prompts.loader import PromptLoader
        from codeograph.passes.pass1.annotator import NodeAnnotator
        from codeograph.passes.pass2.synthesizer import CorpusSynthesizer
        from codeograph.llm._prompts_generated import PromptId
        import datetime
        import json

        settings = Settings()
        if not settings.anthropic_api_key:
            click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")

        # Setup Cache & Telemetry
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_backend = SQLiteCacheBackend(settings.cache_dir / "cache.db")
        telemetry_dir = settings.cache_dir / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        
        run_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        corpus_id = corpus.modules[0].name if corpus.modules else "default-corpus"
        emitter_path = telemetry_dir / f"run-{corpus_id}-{run_ts}.jsonl"
        emitter = JsonlEmitter(emitter_path)

        # Base Provider
        # TODO(learner): handle other providers from settings.llm_provider
        base_provider = AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        )
        retry_policy = RetryPolicy() # default policy
        prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

        # Load graph from Pass 0
        graph_path = out_dir / "graph.json"
        with open(graph_path, "r", encoding="utf-8") as f:
            graph_data = json.load(f)
        nodes = graph_data.get("nodes", [])

        # --- Pass 1: Annotate Nodes ---
        click.echo("Running Pass 1 (Node Annotation)...")
        prompt_p1 = prompt_loader.get(PromptId.ANNOTATE_NODE)
        ctx_p1 = CallContext(
            purpose=Purpose.ANNOTATE,
            prompt_id=PromptId.ANNOTATE_NODE,
            prompt_version=prompt_p1.metadata.version if hasattr(prompt_p1, 'metadata') else "v1",
            prompt_content_hash=prompt_p1.metadata.content_hash_pin if hasattr(prompt_p1, 'metadata') else "TODO",
            corpus_id=corpus_id,
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
            prompt_version=prompt_p2.metadata.version if hasattr(prompt_p2, 'metadata') else "v1",
            prompt_content_hash=prompt_p2.metadata.content_hash_pin if hasattr(prompt_p2, 'metadata') else "TODO",
            corpus_id=corpus_id,
        )
        provider_p2 = build_default_stack(base_provider, retry_policy, cache_backend, emitter, ctx_p2)
        synthesizer = CorpusSynthesizer(provider_p2, prompt_loader, out_dir)
        try:
            synthesizer.synthesize(graph_path, out_dir / "llm-annotations.json")
        except Exception as e:
            click.echo(f"Pass 2 failed: {e}")
            raise

        # Note: We need to update manifest with cache stats and llm_annotations
        # TODO(learner): Update manifest.json with cache stats and sha256 of new outputs
        click.echo("LLM passes complete.")

    finally:
        if corpus is not None:
            acquirer.cleanup(corpus)
