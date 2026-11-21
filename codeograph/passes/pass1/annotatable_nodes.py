"""Which graph nodes Pass 1 annotates — the one rule the enricher and the pre-flight estimate share."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Pass 1 annotates each enclosing type in one LLM call (ADR-005). Method and field nodes have source
# ranges too, but are not annotated independently: their behaviour is folded into the enclosing type's
# `methods[]` response. Module nodes are not separate annotation units either.
SOURCE_BEARING_KINDS = frozenset({"class", "interface", "enum", "record", "annotation_type"})


def select_annotatable_nodes(nodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the nodes Pass 1 sends to the model, in graph order."""
    return [n for n in nodes if n.get("kind") in SOURCE_BEARING_KINDS]
