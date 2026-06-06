"""Pydantic schema for the run manifest.

Per ADR-022 Fork 7: Pydantic is the source of truth; the committed JSON Schema
at ``codeograph/_generated/manifest.schema.json`` is regenerated from Pydantic
via ``Manifest.model_json_schema()`` and pinned by a CI freshness gate.

Per ADR-022 Fork 1: strict-additive discipline applies within ``1.x.x`` —
no remove, rename, type-change, or required/optional flip without a ``2.0.0``
major bump + superseding ADR.

Per ADR-022 Fork 2: every field belongs to one of three categories —
scalar metadata, aggregate metadata, or payload pointer. The ``Manifest``
class below groups fields by category for reviewer clarity.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Base classes — one per manifest-field category (ADR-022 Fork 2)
# ---------------------------------------------------------------------------


class ManifestAggregate(BaseModel):
    """Base for small typed rollup blocks (≤ 20 nested fields total).

    Aggregate blocks describe tightly-coupled rollups of one run; they do
    not grow linearly with corpus size and are not independently consumed
    by external tooling. Subclasses live in this module.
    """

    model_config = ConfigDict(extra="forbid")


class ManifestPointer(BaseModel):
    """Base for {path, sha256, +1 optional extra} payload-pointer records.

    Pointer records reference files that grow linearly with corpus size
    (artefacts), are independently consumed by external tooling (scorecards),
    or need tamper-evidence (compile-check sidecars).
    """

    model_config = ConfigDict(extra="forbid")

    path: str  # PurePosixPath-shaped string; relative to the manifest's directory
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Concrete aggregates and pointers
# ---------------------------------------------------------------------------


class CacheStats(ManifestAggregate):
    """Per-LLM-pass cache behaviour rollup.

    Shape preserved verbatim from shipped
    ``codeograph/graph/models/manifest_schema.py`` per ADR-022 Fork 1's
    strict-additive rule. Five flat fields, keyed by pass name
    (``"pass_1"``, ``"pass_2"``) at the ``Manifest.cache_stats`` level.
    """

    calls: int
    hits: int
    hit_rate: float
    saved_usd_est: float
    incurred_usd_est: float


class ArtefactPointer(ManifestPointer):
    """Pointer to a corpus-sized artefact (graph.json, llm-annotations.json)."""


class ScorecardPointer(ManifestPointer):
    """Pointer to a scorecard JSON file written by ``codeograph eval``."""

    overall: str = Field(pattern=r"^(pass|fail|skip|mixed)$")


class CompileChecksPointer(ManifestPointer):
    """Pointer to a compile-check sidecar log per renderer target."""


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------


class Manifest(BaseModel):
    """Top-level run manifest.

    Fields grouped by ADR-022 Fork 2 category:

    * **Scalar metadata** — single primitive values describing the run as a
      whole (``schema_version``, ``codeograph_version``, ``source_path``,
      ``corpus_id``, ``run_id``).
    * **Aggregate metadata** — small typed rollups tightly coupled to this
      run (``cache_stats`` keyed by pass name).
    * **Payload pointers** — references to files that grow with the corpus
      or are independently consumed (``artefacts``, ``scorecards``,
      ``compile_checks``).
    """

    model_config = ConfigDict(extra="forbid")

    # --- scalar metadata ---
    schema_version: str
    codeograph_version: str
    source_path: str
    corpus_id: str
    run_id: str | None = None  # str | None preserved from shipped state (1.7.0)

    # --- aggregate metadata ---
    cache_stats: dict[str, CacheStats] | None = None  # keyed by pass name, e.g. "pass_1"

    # --- payload pointers ---
    artefacts: dict[str, ArtefactPointer] = Field(default_factory=dict)
    scorecards: dict[str, ScorecardPointer] | None = None
    compile_checks: dict[str, CompileChecksPointer] | None = None


__all__ = [
    "ArtefactPointer",
    "CacheStats",
    "CompileChecksPointer",
    "Manifest",
    "ManifestAggregate",
    "ManifestPointer",
    "ScorecardPointer",
]
