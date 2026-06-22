"""
LlmCorpusEnricher — orchestrates the LLM Pass 1 & Pass 2 semantic analysis pipeline for a corpus.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

import click

from codeograph.config.settings import Settings
from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.factory import build_default_stack
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.models import CallContext, Purpose
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.resolver import LlmProviderResolver
from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.models import CacheStats
from codeograph.passes.pass1.node_annotator import NodeAnnotator
from codeograph.passes.pass2.corpus_synthesizer import CorpusSynthesizer
from codeograph.telemetry.session_manager import TelemetrySessionManager
from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator


class LlmCorpusEnricher:
    """Orchestrates LLM Pass 1 & Pass 2 semantic analysis for a fully-analyzed corpus."""

    def __init__(
        self,
        settings: Settings,
        provider_resolver: LlmProviderResolver,
        telemetry_manager: TelemetrySessionManager,
        stats_aggregator: TelemetryStatsAggregator,
    ) -> None:
        self._settings = settings
        self._provider_resolver = provider_resolver
        self._telemetry_manager = telemetry_manager
        self._stats_aggregator = stats_aggregator

    def enrich(
        self,
        corpus_id: str,
        run_id: str,
        graph_artefact: GraphArtefact,
        out_dir: Path,
    ) -> tuple[GraphArtefact, dict[str, CacheStats] | None]:
        """Run the LLM passes to enrich the deterministic graph with semantic metadata.

        :param corpus_id:      Name of the corpus being enriched.
        :param graph_artefact: GraphArtefact from Pass 0 containing graph.json path and hash.
        :param out_dir:        Output directory to write llm-annotations.json into.
        :returns:              A tuple of:
                                 - :class:`GraphArtefact` representing llm-annotations.json.
                                 - Dict of pass names to :class:`CacheStats` aggregates.
        :raises click.ClickException: If LLM execution succeeds but output file is missing.
        """
        from codeograph.logging_config import RunIdLoggerAdapter

        run_logger = RunIdLoggerAdapter(logger, run_id)
        run_logger.info(
            "LlmCorpusEnricher: starting semantic enrichment for corpus %s",
            corpus_id,
            extra={"context": {"area": "enricher"}},
        )

        if not self._settings.anthropic_api_key:
            click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")

        # Setup Cache & Telemetry Session
        session = self._telemetry_manager.start_session(corpus_id, run_id)

        # Resolve LLM provider
        base_provider = self._provider_resolver.resolve()

        retry_policy = RetryPolicy()  # default policy
        prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

        # Load graph from Pass 0
        with open(graph_artefact.path, encoding="utf-8") as f:
            graph_data = json.load(f)
        nodes = graph_data.get("nodes", [])

        try:
            # --- Pass 1: Annotate Nodes ---
            run_logger.info(
                "LlmCorpusEnricher: starting Pass 1 (Node Annotation)",
                extra={"context": {"area": "enricher"}},
            )
            click.echo("Running Pass 1 (Node Annotation)...")
            prompt_p1 = prompt_loader.get(PromptId.ANNOTATE_NODE)
            ctx_p1 = CallContext(
                run_id=run_id,
                pipeline_name="pass_1",
                pipeline_run_id=run_id,
                purpose=Purpose.ANNOTATE,
                prompt_id=PromptId.ANNOTATE_NODE,
                prompt_version=prompt_p1.metadata.version,
                prompt_content_hash=prompt_p1.metadata.content_hash_pin,
                corpus_id=corpus_id,
                provider_name=self._settings.llm_provider,
            )
            provider_p1 = build_default_stack(
                base_provider, retry_policy, session.cache_backend, session.emitter, ctx_p1
            )
            annotator = NodeAnnotator(
                provider_p1,
                prompt_loader,
                out_dir,
                self._settings.llm_concurrency,
                self._settings.max_pass1_failure_ratio,
            )
            annotations = annotator.annotate(nodes)

            # --- Pass 2: Synthesize Corpus ---
            run_logger.info(
                "LlmCorpusEnricher: starting Pass 2 (Corpus Synthesis)",
                extra={"context": {"area": "enricher"}},
            )
            click.echo("Running Pass 2 (Corpus Synthesis)...")
            prompt_p2 = prompt_loader.get(PromptId.SYNTHESIZE_CORPUS)
            ctx_p2 = CallContext(
                run_id=run_id,
                pipeline_name="pass_2",
                pipeline_run_id=run_id,
                purpose=Purpose.SYNTHESIZE,
                prompt_id=PromptId.SYNTHESIZE_CORPUS,
                prompt_version=prompt_p2.metadata.version,
                prompt_content_hash=prompt_p2.metadata.content_hash_pin,
                corpus_id=corpus_id,
                provider_name=self._settings.llm_provider,
            )
            provider_p2 = build_default_stack(
                base_provider, retry_policy, session.cache_backend, session.emitter, ctx_p2
            )
            synthesizer = CorpusSynthesizer(provider_p2, prompt_loader, out_dir)
            synthesizer.synthesize(annotations, graph_data)
        finally:
            session.emitter.close()

        click.echo("LLM passes complete.")

        # --- Compute the llm-annotations artefact from the just-written file.
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
        cache_stats = self._stats_aggregator.aggregate(session.emitter_path)
        run_logger.info(
            "LlmCorpusEnricher: semantic enrichment complete",
            extra={"context": {"area": "enricher"}},
        )

        return llm_annotations_artefact, cache_stats
