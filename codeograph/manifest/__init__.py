"""Manifest package — Pydantic schema, IO, and run-id generation.

Source of truth for the run-manifest contract. Per ADR-022 Fork 7 the Pydantic
class is the source of truth; the committed JSON Schema at
``codeograph/_generated/manifest.schema.json`` is regenerated from Pydantic via
``Manifest.model_json_schema()`` and pinned by a CI freshness gate.

The strict-additive discipline of ADR-022 Fork 1 applies to the ``Manifest``
schema within ``1.x.x`` — no remove, rename, type-change, or required/
optional flip without a ``2.0.0`` major bump + superseding ADR.
"""

from codeograph.manifest.io import read, write
from codeograph.manifest.run_id import RUN_ID_PATTERN, generate_run_id
from codeograph.manifest.schema import (
    ArtefactPointer,
    CacheStats,
    CompileChecksPointer,
    Manifest,
    ManifestAggregate,
    ManifestPointer,
    ScorecardPointer,
)

__all__ = [
    "ArtefactPointer",
    "CacheStats",
    "CompileChecksPointer",
    "Manifest",
    "ManifestAggregate",
    "ManifestPointer",
    "RUN_ID_PATTERN",
    "ScorecardPointer",
    "generate_run_id",
    "read",
    "write",
]
