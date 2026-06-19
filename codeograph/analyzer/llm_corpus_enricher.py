"""
LlmCorpusEnricher — orchestrates the LLM Pass 1 & Pass 2 semantic analysis pipeline for a corpus.
"""

from __future__ import annotations

from pathlib import Path

from codeograph.config.settings import Settings
from codeograph.llm.resolver import LlmProviderResolver
from codeograph.telemetry.session_manager import TelemetrySessionManager
from codeograph.telemetry.stats_aggregator import TelemetryStatsAggregator
from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.schema import CacheStats


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
        # TODO: The learner should implement the main orchestration logic here.
        # This includes:
        # 1. Resolving the LLM provider using self._provider_resolver.resolve().
        # 2. Starting the telemetry session using self._telemetry_manager.start_session(corpus_id).
        # 3. Loading graph_data and run node annotations (Pass 1) and corpus synthesis (Pass 2).
        # 4. Creating the output GraphArtefact for the llm-annotations.json file.
        # 5. closing/flushing the emitter and aggregating stats via self._stats_aggregator.aggregate().
        raise NotImplementedError("LlmCorpusEnricher.enrich needs to be implemented by the learner.")
