from __future__ import annotations

import json
import logging
import re
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
# Per ADR-005 D-005-6: absolute failure threshold for small batches (total < 10).
_MIN_FAILURES_FOR_ABORT = 3
# Floor below which ratio-gate does not apply (D-005-6 N-floor).
_N_FLOOR = 10
# Cap on distinct failure reasons logged before a ratio/absolute abort raises.
_MAX_LOGGED_FAILURE_SAMPLES = 5

# Regex to extract Java method signatures for the signatures-only fallback (DC2-02).
# Non-capturing group avoids finditer returning only the access-modifier capture.
_METHOD_SIG_RE = re.compile(
    r"(?:public|private|protected|static|final|abstract|synchronized|native)"
    r"\s+[\w<>,?\[\] ]+\s+\w+\s*\([^)]*\)"
    r"\s*(?:throws\s+[\w,\s]+)?\s*[{;]"
)


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

        # Partition: normal vs oversized (signatures-only degraded path, ADR-005 D-005-1)
        normal: list[dict[str, Any]] = []
        degraded_nodes: list[dict[str, Any]] = []
        for node in nodes:
            source = node.get("source_code", "")
            if len(source) > _MAX_SOURCE_CHARS:
                logger.warning(
                    "Node %s exceeds max source chars (%d > %d) — extracting signatures only",
                    node.get("id"),
                    len(source),
                    _MAX_SOURCE_CHARS,
                )
                sigs = _extract_signatures(source)
                node["signatures"] = sigs
                node["extraction_mode"] = "signatures_only"
                degraded_nodes.append(node)
            else:
                normal.append(node)

        def _build_messages(source_body: str, node: dict[str, Any]) -> list[Message]:
            user_text = render(
                prompt.user,
                node_id=node.get("id", ""),
                node_name=node.get("name", ""),
                source_body=source_body,
                category=node.get("category", "UNKNOWN"),
                dependencies=", ".join(d.get("name", "") for d in node.get("dependencies", {}).get("injected", []))
                or "none",
            )
            return [
                Message(role="system", content=prompt.system, cache=CacheHint(ttl="1h")),
                Message(role="user", content=user_text),
            ]

        # Build (messages, schema) request tuples — normal nodes use full source,
        # oversized nodes use their extracted method signatures (ADR-005 D-005-1).
        normal_requests: list[tuple[list[Message], type[NodeAnnotation]]] = [
            (_build_messages(node.get("source_code", ""), node), NodeAnnotation) for node in normal
        ]
        sig_requests: list[tuple[list[Message], type[NodeAnnotation]]] = [
            (
                _build_messages("\n".join(node.get("signatures") or []) or "(no extractable signatures)", node),
                NodeAnnotation,
            )
            for node in degraded_nodes
        ]

        logger.info(
            "Pass 1: annotating %d node(s) (%d signatures-only), max_concurrent=%d",
            len(normal),
            len(degraded_nodes),
            self._max_concurrent,
        )

        all_results = self._provider.complete_structured_many(
            tier=Tier.FAST,
            requests=normal_requests + sig_requests,
            max_concurrent=self._max_concurrent,
        )

        from codeograph.llm.errors import LlmError

        normal_results = all_results[: len(normal)]
        sig_results = all_results[len(normal) :]

        # Failure ratio counts only normal nodes (oversized are already degraded).
        failures = sum(1 for r in normal_results if isinstance(r, LlmError))
        total = len(normal_requests)

        if total >= _N_FLOOR:
            ratio = failures / total
            if ratio > self._max_pass1_failure_ratio:
                _log_failure_sample(normal, normal_results, LlmError)
                raise LlmError(f"Pass 1 failure ratio {ratio:.2f} exceeds max {self._max_pass1_failure_ratio}")
        elif failures > _MIN_FAILURES_FOR_ABORT:
            _log_failure_sample(normal, normal_results, LlmError)
            raise LlmError(
                f"Pass 1 failures ({failures}) exceeds absolute minimum"
                f" ({_MIN_FAILURES_FOR_ABORT}) for batch size {total}"
            )

        # Assemble output — normal nodes first, then signatures-only (oversized).
        # Each entry is an AnnotationRecord envelope (orchestrator-owned `degraded`
        # and `extraction_mode` are separated from the LLM-response NodeAnnotation).
        records: list[dict[str, Any]] = []
        for node, result in zip(normal, normal_results):
            if isinstance(result, LlmError):
                logger.warning("Pass 1 node %s failed: %s", node.get("id"), result)
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
                    node_id=str(node.get("id", "")),
                    degraded=False,
                    annotation=annotation,
                ).model_dump()
            )

        for node, result in zip(degraded_nodes, sig_results):
            node_id = str(node.get("id", ""))
            if isinstance(result, LlmError):
                logger.warning("Pass 1 signatures-only node %s failed: %s", node_id, result)
                records.append(
                    AnnotationRecord(
                        node_id=node_id,
                        degraded=True,
                        annotation=None,
                        extraction_mode="signatures_only",
                    ).model_dump()
                )
                continue

            sig_annotation: NodeAnnotation = result.value
            records.append(
                AnnotationRecord(
                    node_id=node_id,
                    degraded=True,
                    annotation=sig_annotation,
                    extraction_mode="signatures_only",
                ).model_dump()
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / "llm-annotations.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
        logger.info("Pass 1 complete — %d records written to %s", len(records), out_path)

        return records


def _log_failure_sample(nodes: list[dict[str, Any]], results: list[Any], error_type: type) -> None:
    """Log up to N distinct failure reasons before a ratio/absolute abort raises.

    Without this, a total-batch failure (e.g. bad model id, auth) surfaces only
    the generic ratio message in logs.jsonl — the real per-call exception is
    never written anywhere (2026-07-06 manual-run finding MR-02).
    """
    seen: set[str] = set()
    logged = 0
    for node, result in zip(nodes, results):
        if logged >= _MAX_LOGGED_FAILURE_SAMPLES:
            break
        if not isinstance(result, error_type):
            continue
        reason = str(result)
        if reason in seen:
            continue
        seen.add(reason)
        logger.warning("Pass 1 node %s failed: %s", node.get("id"), reason)
        logged += 1


def _extract_signatures(source_code: str) -> list[str]:
    """Extract Java method signatures from source code using regex (signatures-only fallback)."""
    return [m.group(0).strip() for m in _METHOD_SIG_RE.finditer(source_code)]
