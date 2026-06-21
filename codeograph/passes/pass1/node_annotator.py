import json
import logging
from pathlib import Path
from typing import Any

from codeograph.llm._prompts_generated import PromptId
from codeograph.llm.models import CacheHint, Message, Tier
from codeograph.llm.prompts.loader import PromptLoader
from codeograph.llm.prompts.renderer import render
from codeograph.llm.provider import LlmProvider
from codeograph.passes.pass1.models import AnnotationRecord, NodeAnnotation

logger = logging.getLogger(__name__)

# Per ADR-005 §3: oversized nodes are skipped rather than truncated.
_MAX_SOURCE_CHARS = 240_000


class NodeAnnotator:
    def __init__(
        self,
        provider: LlmProvider,
        prompt_loader: PromptLoader,
        output_dir: Path,
        max_concurrent: int = 5,
        max_pass1_failure_ratio: float = 0.10,
    ):
        self._provider = provider
        self._prompt_loader = prompt_loader
        self._output_dir = output_dir
        self._max_concurrent = max_concurrent
        self._max_pass1_failure_ratio = max_pass1_failure_ratio

    def annotate(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Run Pass 1 over all graph nodes.

        Args:
            nodes: List of graph node dicts from graph.json (Pass 0 output).

        Returns:
            List of AnnotationRecord dicts written to llm-annotations.json.
            Each record wraps either a successful NodeAnnotation or a degraded marker.
        """
        prompt = self._prompt_loader.get(PromptId.ANNOTATE_NODE)

        # Partition: normal vs degraded (oversized)
        normal: list[dict[str, Any]] = []
        degraded_ids: list[str] = []
        for node in nodes:
            source = node.get("source_code", "")
            if len(source) > _MAX_SOURCE_CHARS:
                logger.warning(
                    "Node %s exceeds max source chars (%d > %d) — marking degraded",
                    node.get("id"),
                    len(source),
                    _MAX_SOURCE_CHARS,
                )
                # TODO(learner): implement signatures-only extraction and extraction_mode tagging (ADR-005 O3, DC2-02)
                degraded_ids.append(str(node.get("id", "")))
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
                dependencies=", ".join(d.get("name", "") for d in node.get("dependencies", {}).get("injected", []))
                or "none",
            )
            messages: list[Message] = [
                Message(role="system", content=prompt.system, cache=CacheHint(ttl="1h")),
                Message(role="user", content=user_text),
            ]
            requests.append((messages, NodeAnnotation))

        logger.info(
            "Pass 1: annotating %d node(s) (%d degraded), max_concurrent=%d",
            len(normal),
            len(degraded_ids),
            self._max_concurrent,
        )

        results = self._provider.complete_structured_many(
            tier=Tier.FAST,
            requests=requests,
            max_concurrent=self._max_concurrent,
        )

        from codeograph.llm.errors import LlmError

        failures = sum(1 for r in results if isinstance(r, LlmError))
        total = len(requests)

        if total >= 10:
            ratio = failures / total
            if ratio > self._max_pass1_failure_ratio:
                raise LlmError(f"Pass 1 failure ratio {ratio:.2f} exceeds max {self._max_pass1_failure_ratio}")

        # Assemble output — normal nodes first, then degraded stubs.
        # Each entry is an AnnotationRecord envelope (orchestrator-owned `degraded`
        # is separated from the LLM-response NodeAnnotation per ADR-005 O3).
        records: list[dict[str, Any]] = []
        for node, result in zip(normal, results):
            if isinstance(result, LlmError):
                logger.warning("Pass 1 node %s failed: %s", node.get("id"), result)
                # TODO(learner): how should failed nodes be recorded? Fallback to degraded for now.
                records.append(
                    AnnotationRecord(
                        node_id=str(node.get("id", "")),
                        degraded=True,
                        annotation=None,
                    ).model_dump()
                )
                continue

            annotation: NodeAnnotation = result.value
            records.append(
                AnnotationRecord(
                    node_id=annotation.node_id,
                    degraded=False,
                    annotation=annotation,
                ).model_dump()
            )

        for d_id in degraded_ids:
            records.append(
                AnnotationRecord(
                    node_id=d_id,
                    degraded=True,
                    annotation=None,
                ).model_dump()
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / "llm-annotations.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
        logger.info("Pass 1 complete — %d records written to %s", len(records), out_path)

        return records
