"""Manifest package — Pydantic schema (manifest ``2.0.0``, flat layout), IO, and run-id generation.

Source of truth for the run-manifest contract. Per ADR-022 Fork 7 the Pydantic
class is the source of truth; the committed JSON Schema at
``codeograph/_generated/manifest.schema.json`` is regenerated from Pydantic via
``Manifest.model_json_schema()`` and pinned by a CI freshness gate.

The strict-additive discipline of **ADR-025 Fork 1** applies to the ``Manifest``
schema within ``2.x.x`` — no remove, rename, type-change, restructure, or
required/optional flip without a ``3.0.0`` major bump + superseding ADR. The
shipped ``1.7.0`` nested layout was a deliberate ``2.0.0`` restructure
(ADR-025; supersedes ADR-022's manifest-schema decisions; ADR-022's
structured-logging decisions are unaffected).
"""

from codeograph.manifest.io import read, write
from codeograph.manifest.run_id import RUN_ID_PATTERN, generate_run_id
from codeograph.manifest.schema import (
    ArtefactPointer,
    CacheStats,
    CompileChecksPointer,
    Manifest,
    ScorecardPointer,
)

__all__ = [
    "ArtefactPointer",
    "CacheStats",
    "CompileChecksPointer",
    "Manifest",
    "RUN_ID_PATTERN",
    "ScorecardPointer",
    "generate_run_id",
    "read",
    "write",
]
