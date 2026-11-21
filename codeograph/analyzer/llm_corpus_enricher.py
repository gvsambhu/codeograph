"""
LlmCorpusEnricher — orchestrates the LLM Pass 1 & Pass 2 semantic analysis pipeline for a corpus.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import click

from codeograph.config.settings import Settings
from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.factory import build_default_stack
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.models import CallContext, ProviderType, Purpose
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.resolver import LlmProviderResolver
from codeograph.logging_config import RunIdLoggerAdapter
from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.models import CacheStats
from codeograph.passes.pass1.annotatable_nodes import select_annotatable_nodes
from codeograph.passes.pass1.node_annotator import NodeAnnotator
from codeograph.passes.pass1.node_source_loader import NodeSourceLoader
from codeograph.passes.pass2.corpus_synthesizer import (
    CORPUS_SYNTHESIS_FILENAME,
    CORPUS_SYNTHESIS_SCHEMA_VERSION,
    CorpusSynthesizer,
)
from codeograph.telemetry.session_manager import TelemetrySessionManager
from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator

logger = logging.getLogger(__name__)


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
        corpus_root: Path,
    ) -> tuple[GraphArtefact, GraphArtefact, dict[str, CacheStats] | None]:
        """Run the LLM passes to enrich the deterministic graph with semantic metadata.

        :param corpus_id:      Name of the corpus being enriched.
        :param graph_artefact: GraphArtefact from Pass 0 containing graph.json path and hash.
        :param out_dir:        Output directory to write llm-annotations.json and
                                corpus-synthesis.json into.
        :param corpus_root:    Root of the source corpus on disk — resolves each node's
                                `source_file` so Pass 1 can read the real class source
                                (ADR-005; NodeSourceLoader).
        :returns:              A tuple of:
                                 - :class:`GraphArtefact` representing llm-annotations.json.
                                 - :class:`GraphArtefact` representing corpus-synthesis.json.
                                 - Dict of pass names to :class:`CacheStats` aggregates.
        :raises click.ClickException: If LLM execution succeeds but an output file is missing.
        """
        run_logger = RunIdLoggerAdapter(logger, run_id)
        run_logger.info(
            "LlmCorpusEnricher: starting semantic enrichment for corpus %s",
            corpus_id,
            extra={"context": {"area": "enricher"}},
        )

        provider = self._settings.llm_provider
        if provider == ProviderType.ANTHROPIC and not self._settings.anthropic_api_key:
            click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")
        elif provider == ProviderType.OPENROUTER and not self._settings.openrouter_api_key:
            click.echo("WARNING: CODEOGRAPH_OPENROUTER_API_KEY is not set. LLM passes will fail unless mocked.")
        elif provider == ProviderType.OPENAI_COMPATIBLE and not self._settings.openai_compat_api_key:
            click.echo("WARNING: CODEOGRAPH_OPENAI_COMPAT_API_KEY is not set. LLM passes will fail unless mocked.")

        # Setup Cache & Telemetry Session
        session = self._telemetry_manager.start_session(corpus_id, run_id)

        # Resolve LLM provider
        base_provider = self._provider_resolver.resolve()

        retry_policy = RetryPolicy()  # default policy
        prompt_loader = PromptLoader(Path(__file__).parent.parent / "prompts")

        # Load graph from Pass 0 (read-only: the graph is never rewritten)
        with open(graph_artefact.path, encoding="utf-8") as f:
            graph_data = json.load(f)

        # ADR-005: Pass 1 annotates classes, not methods/fields/modules — those never
        # carry source_file/line_range worth a standalone LLM call. Load the real source
        # body for the nodes that remain (NodeSourceLoader; 2026-07-06 manual-run finding).
        # Shallow-copy each node: source_code is a Pass-1-only input, never part of the
        # committed graph.schema.json — mutating the shared dicts would leak it into
        # graph_data (extra='forbid' violation if it were ever serialised).
        nodes = [dict(n) for n in select_annotatable_nodes(graph_data.get("nodes", []))]
        NodeSourceLoader(corpus_root).load(nodes)

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
                provider_name=self._settings.resolved_provider_label,
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
                provider_name=self._settings.resolved_provider_label,
            )
            provider_p2 = build_default_stack(
                base_provider, retry_policy, session.cache_backend, session.emitter, ctx_p2
            )
            synthesizer = CorpusSynthesizer(provider_p2, prompt_loader, out_dir)
            synthesizer.synthesize(annotations)
        finally:
            session.emitter.close()

        click.echo("LLM passes complete.")

        # --- Compute both artefacts from the just-written files.
        llm_annotations_artefact = self._artefact_of_written_file(
            out_dir / "llm-annotations.json",
            schema_version=graph_artefact.schema_version,  # same version as graph in v1
            label="LLM annotations file",
        )
        corpus_synthesis_artefact = self._artefact_of_written_file(
            out_dir / CORPUS_SYNTHESIS_FILENAME,
            schema_version=CORPUS_SYNTHESIS_SCHEMA_VERSION,
            label="corpus synthesis file",
        )

        # --- Aggregate cache_stats from telemetry.
        cache_stats = self._stats_aggregator.aggregate(session.emitter_path)
        run_logger.info(
            "LlmCorpusEnricher: semantic enrichment complete",
            extra={"context": {"area": "enricher"}},
        )

        return llm_annotations_artefact, corpus_synthesis_artefact, cache_stats

    @staticmethod
    def _artefact_of_written_file(path: Path, *, schema_version: str, label: str) -> GraphArtefact:
        """Describe a file the LLM passes just wrote: its path, schema version and sha256.

        :raises click.ClickException: If the passes reported success but wrote no file.
        """
        if not path.exists():
            raise click.ClickException(
                f"The LLM passes reported success but wrote no {label} ({path}). This is a producer bug."
            )
        return GraphArtefact(
            path=path,
            schema_version=schema_version,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
