import json
import logging
from pathlib import Path
from typing import Any

from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.models import CacheHint, Message, Tier
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render
from codeograph.llm.provider import LlmProvider
from codeograph.passes.pass2.models import SynthesisResult

logger = logging.getLogger(__name__)


class CorpusSynthesizer:
    def __init__(
        self,
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        output_dir: Path,
    ):
        self._provider = provider
        self._prompt_loader = prompt_loader
        self._output_dir = output_dir

    def synthesize(self, records: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
        """
        Run Pass 2 — single LLM call over aggregated Pass 1 annotations.

        Args:
            records: List of AnnotationRecord dicts from Pass 1 (llm-annotations.json).
                     Each record is an envelope: {node_id, degraded, annotation}.
            graph:   graph.json dict from Pass 0 (read by the caller).

        Returns:
            SynthesisResult dict written back into graph.json as top-level enrichments.
        """
        prompt = self._prompt_loader.get(PromptId.SYNTHESIZE_CORPUS)

        # Build a compact text summary — no source code, low token cost (per legacy pattern).
        # Domain key comes from the nested annotation; degraded records get a "unknown" bucket
        # and are rendered with a [DEGRADED] marker.
        domain_map: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            ann = rec.get("annotation") or {}
            domain = ann.get("domain_hint", "unknown")
            domain_map.setdefault(domain, []).append(rec)

        lines: list[str] = []
        for domain, recs in domain_map.items():
            lines.append(f"Domain: {domain}")
            for rec in recs:
                ann = rec.get("annotation") or {}
                class_name = ann.get("class_name", "?")
                if rec.get("degraded"):
                    lines.append(f"  {class_name} [DEGRADED]")
                    continue
                desc = ann.get("description", "")
                stereotype = ann.get("stereotype") or "UNKNOWN"
                lines.append(f"  {class_name} [{stereotype}]: {desc}")
            lines.append("")

        compact_summary = "\n".join(lines)
        domain_names = ", ".join(sorted(domain_map.keys()))

        user_text = render(
            prompt.user,
            domain_names=domain_names,
            compact_summary=compact_summary,
        )

        messages: list[Message] = [
            Message(role="system", content=prompt.system, cache=CacheHint(ttl="1h")),
            Message(role="user", content=user_text),
        ]

        logger.info("Pass 2: synthesising corpus across %d domain(s)", len(domain_map))
        result = self._provider.complete_structured(
            tier=Tier.DEEP,
            messages=messages,
            schema=SynthesisResult,
        )

        synthesis: SynthesisResult = result.value
        synthesis_dict = synthesis.model_dump()

        # Write enrichments back into graph top-level (per ADR-015 design)
        graph["projectOverview"] = {
            "description": synthesis.description,
            "architecturePattern": synthesis.architecture_pattern,
            "domains": synthesis.domains,
            "crossDomainDependencies": [dep.model_dump() for dep in synthesis.cross_domain_dependencies],
        }

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / "graph.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(graph, fh, indent=2, ensure_ascii=False)
        logger.info("Pass 2 complete — graph enriched and written to %s", out_path)

        return synthesis_dict
