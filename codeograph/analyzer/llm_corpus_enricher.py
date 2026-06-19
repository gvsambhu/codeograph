"""
LlmCorpusEnricher — orchestrates the LLM Pass 1 & Pass 2 semantic analysis pipeline for a corpus.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import click

from codeograph.config.settings import Settings
from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
from codeograph.llm.factory import build_default_stack
from codeograph.llm.middleware.retry_policy import RetryPolicy
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.providers.anthropic_provider import AnthropicProvider
from codeograph.llm.types import CallContext, ProviderType, Purpose, Tier
from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.schema import CacheStats
from codeograph.passes.pass1.annotator import NodeAnnotator
from codeograph.passes.pass2.synthesizer import CorpusSynthesizer
from codeograph.telemetry.emitter import JsonlEmitter

logger = logging.getLogger(__name__)


class LlmCorpusEnricher:
    """Orchestrates LLM Pass 1 & Pass 2 semantic analysis for a fully-analyzed corpus.

    Stateless after construction. Takes Settings config during initialization.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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
        if not self._settings.anthropic_api_key:
            click.echo("WARNING: CODEOGRAPH_ANTHROPIC_API_KEY is not set. LLM passes will fail unless mocked.")

        # Setup Cache & Telemetry
        self._settings.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_backend = SQLiteCacheBackend(self._settings.cache_dir / "cache.db")
        telemetry_dir = self._settings.cache_dir / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        run_ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        emitter_path = telemetry_dir / f"run-{corpus_id}-{run_ts}.jsonl"
        emitter = JsonlEmitter(emitter_path)

        # Base Provider — dispatches on settings.llm_provider
        tier_map = {
            Tier.FAST: self._settings.llm_model_fast or self._settings.llm_model,
            Tier.DEEP: self._settings.llm_model_deep or self._settings.llm_model,
            Tier.RENDER: self._settings.llm_model_render or self._settings.llm_model,
        }

        match self._settings.llm_provider:
            case ProviderType.ANTHROPIC:
                base_provider = AnthropicProvider(
                    api_key=self._settings.anthropic_api_key.get_secret_value() if self._settings.anthropic_api_key else "",
                    tier_map=tier_map,
                )
            case ProviderType.OLLAMA:
                raise NotImplementedError(
                    "Ollama provider is not implemented in v1. "
                    "Use llm_provider=anthropic; Ollama support is planned for v1.1."
                )
            case ProviderType.BEDROCK:
                raise NotImplementedError(
                    "Bedrock provider is not implemented in v1. "
                    "Use llm_provider=anthropic; Bedrock support is planned for v1.1."
                )
            case _:
                raise ValueError(
                    f"Unknown llm_provider: {self._settings.llm_provider!r}. "
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
            provider_name=self._settings.llm_provider,
        )
        provider_p1 = build_default_stack(base_provider, retry_policy, cache_backend, emitter, ctx_p1)
        annotator = NodeAnnotator(provider_p1, prompt_loader, out_dir, self._settings.llm_concurrency)
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
            provider_name=self._settings.llm_provider,
        )
        provider_p2 = build_default_stack(base_provider, retry_policy, cache_backend, emitter, ctx_p2)
        synthesizer = CorpusSynthesizer(provider_p2, prompt_loader, out_dir)
        synthesizer.synthesize(annotations, graph_data)

        # Flush telemetry so the JSONL is readable for per-pass aggregation.
        emitter.close()
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

        cache_stats = None
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

        return llm_annotations_artefact, cache_stats
