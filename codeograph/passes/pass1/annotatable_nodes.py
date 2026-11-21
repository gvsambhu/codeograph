"""Which graph nodes Pass 1 annotates — the one rule the enricher and the pre-flight estimate share."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Pass 1 makes one LLM call per class — the natural "oversized" unit is the class, not any individual
# method (ADR-005). Method, field and module nodes carry no source_file/line_range worth annotating on
# their own; their behaviour is folded into the class-level call's `methods[]` response.
SOURCE_BEARING_KINDS = frozenset({"class", "interface", "enum", "record", "annotation_type"})


def select_annotatable_nodes(nodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the nodes Pass 1 sends to the model, in graph order."""
    return [n for n in nodes if n.get("kind") in SOURCE_BEARING_KINDS]
