import json
import logging
from pathlib import Path

from codeograph.llm.provider import LlmProvider
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render
from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.types import Message, Tier, CacheHint
from codeograph.passes.pass2.schemas import SynthesisResult

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

    def synthesize(self, annotations: list[dict], graph: dict) -> dict:
        """
        Run Pass 2 — single LLM call over aggregated Pass 1 annotations.

        Args:
            annotations: List of NodeAnnotation dicts from Pass 1 (llm-annotations.json).
            graph:       graph.json dict from Pass 0 (read by the caller).

        Returns:
            SynthesisResult dict written back into graph.json as top-level enrichments.
        """
        prompt = self._prompt_loader.get(PromptId.SYNTHESIZE_CORPUS)

        # Build a compact text summary — no source code, low token cost (per legacy pattern)
        domain_map: dict[str, list[dict]] = {}
        for ann in annotations:
            domain = ann.get("domain_hint", "unknown")
            domain_map.setdefault(domain, []).append(ann)

        lines: list[str] = []
        for domain, nodes in domain_map.items():
            lines.append(f"Domain: {domain}")
            for node in nodes:
                if node.get("degraded"):
                    lines.append(f"  {node.get('class_name', '?')} [DEGRADED]")
                    continue
                desc = node.get("description", "")
                stereotype = node.get("stereotype", "UNKNOWN")
                lines.append(f"  {node.get('class_name', '?')} [{stereotype}]: {desc}")
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
            "crossDomainDependencies": [
                dep.model_dump() for dep in synthesis.cross_domain_dependencies
            ],
        }

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / "graph.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(graph, fh, indent=2, ensure_ascii=False)
        logger.info("Pass 2 complete — graph enriched and written to %s", out_path)

        return synthesis_dict
