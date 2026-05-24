import json
import logging
from pathlib import Path

from codeograph.llm.provider import LlmProvider
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render
from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.types import Message, Tier, CacheHint
from codeograph.passes.pass1.schemas import NodeAnnotation

logger = logging.getLogger(__name__)

# Per ADR-005 §6: oversized nodes are skipped rather than truncated.
_MAX_SOURCE_CHARS = 120_000


class NodeAnnotator:
    def __init__(
        self,
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        output_dir: Path,
        max_concurrent: int = 5,
    ):
        self._provider = provider
        self._prompt_loader = prompt_loader
        self._output_dir = output_dir
        self._max_concurrent = max_concurrent

    def annotate(self, nodes: list[dict]) -> list[dict]:
        """
        Run Pass 1 over all graph nodes.

        Args:
            nodes: List of graph node dicts from graph.json (Pass 0 output).

        Returns:
            List of NodeAnnotation dicts written to llm-annotations.json.
        """
        prompt = self._prompt_loader.get(PromptId.ANNOTATE_NODE)

        # Partition: normal vs degraded (oversized)
        normal, degraded_ids = [], []
        for node in nodes:
            source = node.get("source_code", "")
            if len(source) > _MAX_SOURCE_CHARS:
                logger.warning(
                    "Node %s exceeds max source chars (%d > %d) — marking degraded",
                    node.get("id"), len(source), _MAX_SOURCE_CHARS,
                )
                degraded_ids.append(node.get("id"))
            else:
                normal.append(node)

        # Build (messages, schema) request tuples for concurrent execution
        requests: list[tuple[list[Message], type[NodeAnnotation]]] = []
        for node in normal:
            user_text = render(
                prompt.user,
                node_id=node.get("id", ""),
                node_name=node.get("name", ""),
                source_body=node.get("source_code", ""),
                category=node.get("category", "UNKNOWN"),
                dependencies=", ".join(
                    d.get("name", "") for d in node.get("dependencies", {}).get("injected", [])
                ) or "none",
            )
            messages: list[Message] = [
                Message(role="system", content=prompt.system, cache=CacheHint(ttl="1h")),
                Message(role="user", content=user_text),
            ]
            requests.append((messages, NodeAnnotation))

        logger.info(
            "Pass 1: annotating %d node(s) (%d degraded), max_concurrent=%d",
            len(normal), len(degraded_ids), self._max_concurrent,
        )

        results = self._provider.complete_structured_many(
            tier=Tier.FAST,
            requests=requests,
            max_concurrent=self._max_concurrent,
        )

        # Assemble output — normal nodes first, then degraded stubs
        annotations: list[dict] = []
        for node, result in zip(normal, results):
            annotation: NodeAnnotation = result.value
            annotations.append(annotation.model_dump())

        for node_id in degraded_ids:
            annotations.append(
                NodeAnnotation(
                    node_id=node_id,
                    degraded=True,
                    class_name="",
                    stereotype=None,
                    domain_hint="",
                    description="Skipped: source exceeded size limit.",
                    methods=[],
                ).model_dump()
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / "llm-annotations.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(annotations, fh, indent=2, ensure_ascii=False)
        logger.info("Pass 1 complete — %d annotations written to %s", len(annotations), out_path)

        return annotations
