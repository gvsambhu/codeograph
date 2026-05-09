"""
GraphWriter — serializes a CodeographKnowledgeGraph to disk in canonical form
and produces the accompanying manifest.json.

Output contract (ADR-006 Fork 5 + Fork 6):

    <output_dir>/
    ├── graph.json       ← deterministic, canonical-form JSON (this writer)
    └── manifest.json    ← schema version + SHA-256 of graph.json

llm-annotations.json is produced by a later pipeline stage (DC2) and is not
written here. The manifest entry for it is emitted with sha256=null to signal
that the artefact has not been produced in this run (--ast-only mode).

Canonical-form rules (ADR-006 §"Canonical-form requirement"):
  - json.dumps with sort_keys=True, separators=(",", ":"), ensure_ascii=False
  - Trailing LF newline
  - nodes array sorted by id
  - edges array sorted by (kind, source, target)
  - Within each node: list-valued properties that are semantically unordered
    (modifiers, annotations, implements, extends_interfaces, constants,
    constraints) are sorted before emission. Positionally-ordered lists
    (parameters, components, elements) are preserved as-is.
  - No wall-clock timestamps, run IDs, or absolute filesystem paths in graph.json

The same canonical bytes that are written to disk are used to compute the
SHA-256 recorded in manifest.json and compared byte-for-byte by the golden-
graph regression suite (ADR-007).
"""

from __future__ import annotations

import hashlib
import json
import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph
from codeograph.graph.models.manifest_schema import (
    ArtefactMeta,
    Artefacts,
    CodeographRunManifest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_SCHEMA_VERSION    = "1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"

GRAPH_FILENAME          = "graph.json"
MANIFEST_FILENAME       = "manifest.json"
LLM_ANNOTATIONS_FILENAME = "llm-annotations.json"

# Node list properties that are semantically unordered and must be sorted
# for canonical form. Positional lists (parameters, components, elements)
# are intentionally excluded — their order carries meaning.
_SORTABLE_NODE_ARRAYS = frozenset({
    "modifiers",
    "annotations",
    "implements",
    "extends_interfaces",
    "constants",
    "constraints",
})


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class GraphWriter:
    """
    Serializes a CodeographKnowledgeGraph to disk in canonical form and
    writes the manifest.

    Stateless — no instance state. A single instance can be reused across runs.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        graph: CodeographKnowledgeGraph,
        output_dir: Path,
    ) -> Path:
        """
        Write graph.json and manifest.json to output_dir.

        Creates output_dir (and any parents) if it does not exist.
        Does not overwrite-check — callers are responsible for ensuring
        the output directory is safe to write into (enforced by the CLI
        via the --force flag per ADR-006 D3 output-path safety rule).

        :param graph:      assembled CodeographKnowledgeGraph from GraphAssembler.
        :param output_dir: directory to write artefacts into.
        :returns:          path to manifest.json (conventional entry point for
                           downstream consumers).
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Produce canonical bytes — single source of truth for both the
        # file content and the SHA-256 recorded in the manifest.
        graph_bytes = self._canonical_bytes(graph)
        graph_sha256 = hashlib.sha256(graph_bytes).hexdigest()

        # Write graph.json
        graph_path = output_dir / GRAPH_FILENAME
        graph_path.write_bytes(graph_bytes)
        logger.info(
            "GraphWriter: wrote %s (%d bytes, sha256=%s…)",
            graph_path, len(graph_bytes), graph_sha256[:12],
        )

        # Write manifest.json
        manifest_path = output_dir / MANIFEST_FILENAME
        manifest = self._build_manifest(graph_sha256)
        manifest_bytes = self._manifest_bytes(manifest)
        manifest_path.write_bytes(manifest_bytes)
        logger.info("GraphWriter: wrote %s", manifest_path)

        return manifest_path

    # ------------------------------------------------------------------
    # Canonical serialization
    # ------------------------------------------------------------------

    def _canonical_bytes(self, graph: CodeographKnowledgeGraph) -> bytes:
        """
        Produce the canonical UTF-8 bytes for graph.json.

        Pydantic RootModel serialises each Node / Edge to its unwrapped root
        dict (not {"root": {...}}), so the resulting structure is:
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
                    node[field] = sorted(
                        v for v in node[field] if v is not None
                    )

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

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _build_manifest(self, graph_sha256: str) -> CodeographRunManifest:
        """
        Build the CodeographRunManifest.

        llm_annotations sha256 is None — this writer runs in AST-only mode
        (DC1). The DC2 LLM stage will overwrite the manifest entry when it
        produces llm-annotations.json.
        """
        return CodeographRunManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            codeograph_version=self._tool_version(),
            artefacts=Artefacts(
                graph=ArtefactMeta(
                    path=GRAPH_FILENAME,
                    schema_version=GRAPH_SCHEMA_VERSION,
                    sha256=graph_sha256,
                ),
                llm_annotations=ArtefactMeta(
                    path=LLM_ANNOTATIONS_FILENAME,
                    schema_version=GRAPH_SCHEMA_VERSION,
                    sha256=None,
                ),
            ),
        )

    @staticmethod
    def _manifest_bytes(manifest: CodeographRunManifest) -> bytes:
        """
        Serialize the manifest to canonical UTF-8 bytes.
        Uses the same sort_keys + compact-separators style as graph.json
        for consistency, but the manifest is not subject to the golden-graph
        byte-equal contract (it contains run-specific metadata).
        """
        data = manifest.model_dump(mode="json")
        serialized = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            indent=2,       # manifest is human-readable; indent differs from graph
            ensure_ascii=False,
        )
        return (serialized + "\n").encode("utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_version() -> str:
        """
        Read codeograph package version from installed metadata.
        Falls back to "0.1.0-dev" if the package is not installed
        (e.g. running from source without `pip install -e .`).
        """
        try:
            return version("codeograph")
        except PackageNotFoundError:
            return "0.1.0-dev"
