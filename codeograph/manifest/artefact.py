"""GraphArtefact — the result of writing a deterministic graph (Pass 0).

Lives in the manifest package (not the graph package) because the artefact
shape — ``{path, schema_version, sha256}`` — is the same shape a manifest
``ArtefactPointer`` carries. The graph package *produces* the artefact; the
manifest package *interprets* it. Putting the type in the manifest package
avoids a layering inversion (the lower-level manifest package depending on
the higher-level graph package).

Kept as a small :class:`dataclass` rather than a Pydantic model because it
is a transient in-memory hand-off between two stages of the same process;
it never appears on disk, never gets validated against a JSON Schema, and
never crosses a process boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphArtefact:
    """Result of writing a deterministic graph (Pass 0).

    Consumed by :class:`codeograph.manifest.assembler.ManifestAssembler`
    when it builds the terminal 2.0.0 manifest. The manifest is never
    written by the graph-writing stage per the ADR-025 terminal-write
    protocol amendment: an intermediate manifest is never written, so the
    strict invariants in ADR-025 §Invariants are never transiently
    violated on disk.

    Attributes:
        path:           Path to the just-written graph file on disk.
        schema_version: The file's schema version. Currently always the
                        producing package's ``GRAPH_SCHEMA_VERSION``; the
                        field exists so the manifest pointer
                        (``ArtefactPointer.schema_version``) can be
                        populated by the assembler without inspecting the
                        file.
        sha256:         Hex SHA-256 of the canonical bytes that were
                        written, suitable for the manifest's
                        ``ArtefactPointer.sha256``.
    """

    path: Path
    schema_version: str
    sha256: str


__all__ = ["GraphArtefact"]
