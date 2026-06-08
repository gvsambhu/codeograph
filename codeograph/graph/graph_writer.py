"""
GraphWriter — serializes a CodeographKnowledgeGraph to disk in canonical form.

Output contract (ADR-006 Fork 5 + Fork 6):

    <output_dir>/
    └── graph.json       ← deterministic, canonical-form JSON (this writer)

The manifest.json is NOT written by this module. Per the ADR-025 write-protocol
amendment (the "terminal-write" pattern), the manifest appears only at the
terminal write orchestrated by the ``codeograph run`` command (Pass 1+2
completion for full runs; Pass 0 completion for ``--ast-only``). This module's
``write()`` returns a :class:`GraphArtefact` carrying the path, schema version,
and sha256 of the just-written graph.json; the manifest assembler consumes it.

Canonical-form rules (ADR-006 §"Canonical-form requirement"):
  - ``json.dumps`` with ``sort_keys=True``, ``separators=(",", ":")``,
    ``ensure_ascii=False``
  - Trailing LF newline
  - ``nodes`` array sorted by id
  - ``edges`` array sorted by ``(kind, source, target)``
  - Within each node: list-valued properties that are semantically unordered
    (modifiers, annotations, implements, extends_interfaces, constants,
    constraints) are sorted before emission. Positionally-ordered lists
    (parameters, components, elements) are preserved as-is.
  - No wall-clock timestamps, run IDs, or absolute filesystem paths in graph.json

The same canonical bytes that are written to disk are used to compute the
SHA-256 returned in :attr:`GraphArtefact.sha256` and compared byte-for-byte by
the golden-graph regression suite (ADR-007).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_SCHEMA_VERSION = "1.0.0"

GRAPH_FILENAME = "graph.json"

# Node list properties that are semantically unordered and must be sorted
# for canonical form. Positional lists (parameters, components, elements)
# are intentionally excluded — their order carries meaning.
_SORTABLE_NODE_ARRAYS = frozenset(
    {
        "modifiers",
        "annotations",
        "implements",
        "extends_interfaces",
        "constants",
        "constraints",
    }
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphArtefact:
    """Result of writing the deterministic graph (Pass 0).

    Consumed by the manifest assembler (``codeograph.manifest.assembler``)
    when it builds the terminal 2.0.0 manifest. The manifest is never
    written by this module per the ADR-025 write-protocol amendment (the
    "terminal-write" pattern): an intermediate manifest is never written,
    so the strict invariants in ADR-025 §Invariants are never transiently
    violated on disk.

    Attributes:
        path:           Path to the just-written ``graph.json`` on disk.
        schema_version: The graph file's schema version. Currently always
                        :data:`GRAPH_SCHEMA_VERSION`; the field exists so
                        the manifest pointer (``ArtefactPointer.schema_version``)
                        can be populated by the assembler without inspecting
                        the file.
        sha256:         Hex SHA-256 of the canonical bytes that were
                        written, suitable for the manifest's ``graph``
                        ``ArtefactPointer.sha256``.
    """

    path: Path
    schema_version: str
    sha256: str


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


class GraphWriter:
    """
    Serializes a CodeographKnowledgeGraph to disk in canonical form.

    Stateless — no instance state. A single instance can be reused across runs.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        graph: CodeographKnowledgeGraph,
        output_dir: Path,
    ) -> GraphArtefact:
        """
        Write ``graph.json`` to ``output_dir``.

        Creates ``output_dir`` (and any parents) if it does not exist.
        Does not overwrite-check — callers are responsible for ensuring
        the output directory is safe to write into (enforced by the CLI
        via the ``--force`` flag per ADR-006 D3 output-path safety rule).

        :param graph:        Assembled :class:`CodeographKnowledgeGraph` from
                             :class:`GraphAssembler`.
        :param output_dir:   Directory to write ``graph.json`` into.
        :returns:            :class:`GraphArtefact` carrying the path,
                             schema version, and sha256 of the
                             just-written file. Consumed by the manifest
                             assembler.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Produce canonical bytes — single source of truth for both the
        # file content and the SHA-256 returned in the artefact.
        graph_bytes = self._canonical_bytes(graph)
        graph_sha256 = hashlib.sha256(graph_bytes).hexdigest()

        # Write graph.json
        graph_path = output_dir / GRAPH_FILENAME
        graph_path.write_bytes(graph_bytes)
        logger.info(
            "GraphWriter: wrote %s (%d bytes, sha256=%s…)",
            graph_path,
            len(graph_bytes),
            graph_sha256[:12],
        )

        return GraphArtefact(
            path=graph_path,
            schema_version=GRAPH_SCHEMA_VERSION,
            sha256=graph_sha256,
        )

    # ------------------------------------------------------------------
    # Canonical serialization
    # ------------------------------------------------------------------

    def _canonical_bytes(self, graph: CodeographKnowledgeGraph) -> bytes:
        """
        Produce the canonical UTF-8 bytes for ``graph.json``.

        Pydantic RootModel serialises each Node / Edge to its unwrapped root
        dict (not ``{"root": {...}}``), so the resulting structure is::

            {"edges": [...], "nodes": [...]}

        with each element being the concrete node or edge dict directly.
        """
        data = graph.model_dump(mode="json")

        # Sort nodes by id
        data["nodes"] = sorted(data["nodes"], key=lambda n: n["id"])

        # Sort list-valued properties within each node that are unordered
        for node in data["nodes"]:
            for field in _SORTABLE_NODE_ARRAYS:
                if field in node and isinstance(node[field], list):
                    node[field] = sorted(v for v in node[field] if v is not None)

        # Sort edges by (kind, source, target)
        data["edges"] = sorted(
            data["edges"],
            key=lambda e: (e["kind"], e["source"], e["target"]),
        )

        canonical = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        # ADR-006: trailing LF newline required for canonical form
        return (canonical + "\n").encode("utf-8")
