"""Pydantic schema for the run manifest (manifest ``2.0.0``, flat layout).

Per ADR-025: the manifest is a flat ``2.0.0`` structure with
``artefacts`` / ``scorecards`` / ``compile_checks`` as top-level peers
(ADR-025 Fork 2). Five standalone ``BaseModel`` classes — no shared base —
because ``schema_version`` belongs to ``ArtefactPointer`` only (ADR-025
Fork 4), and the prior shared-base symmetry no longer holds cleanly. The
``2.0.0`` major bump resets the strict-additive discipline to apply
within ``2.x.x`` — no remove, rename, type-change, or required/optional
flip without a ``3.0.0`` and a superseding ADR (ADR-025 Fork 1).

Per ADR-022 Fork 7 (still in force, unaffected by ADR-025): Pydantic is
the source of truth; the committed JSON Schema at
``codeograph/_generated/manifest.schema.json`` is regenerated from
Pydantic via ``Manifest.model_json_schema()`` and pinned by a CI
freshness gate.

Per ADR-022 Fork 2: every field belongs to one of three categories —
scalar metadata, aggregate metadata, or payload pointer. The
``Manifest`` class below groups fields by category for reviewer clarity.

ADR-025 partially supersedes ADR-022's manifest-schema decisions. See
``codeograph/docs/adr/ADR-025-manifest-schema-flat-layout.md`` for the
relationships section. ADR-022's structured-logging decisions are
unaffected.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from codeograph.manifest.run_id import RUN_ID_PATTERN

# ---------------------------------------------------------------------------
# Pointer classes — one per payload-pointer kind (ADR-025 Fork 2)
#
# Each pointer is a standalone ``BaseModel`` with its own
# ``model_config = ConfigDict(extra="forbid")``; no shared base class.
# ``sha256`` is required on every present pointer (ADR-025 Fork 3): the
# ``--ast-only`` state is represented by **omitting** the
# ``llm_annotations`` pointer (and setting top-level ``llm_skipped: true``),
# not by a nullable hash. A null hash is reserved for "this run produced
# no file" *and* is forbidden here.
# ---------------------------------------------------------------------------


class ArtefactPointer(BaseModel):
    """Pointer to a corpus-sized artefact (graph.json, llm-annotations.json).

    Carries its own ``schema_version`` (ADR-025 Fork 4 / ADR-006 manifest-
    as-version-authority contract) so a consumer learns the artefact's
    format version from the manifest without opening the file.
    """

    model_config = ConfigDict(extra="forbid")

    path: str  # POSIX-relative to the manifest's directory
    schema_version: str  # per-artefact format version
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")  # required (ADR-025 Fork 3)


class ScorecardPointer(BaseModel):
    """Pointer to a scorecard JSON file written by ``codeograph eval``.

    Top-level peer of ``artefacts`` (ADR-025 Fork 2): scorecards are
    evaluation outputs, not pipeline artefacts. ``overall`` carries the
    discriminated-union threshold result.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    overall: str = Field(pattern=r"^(pass|fail|skip|mixed)$")


class CompileChecksPointer(BaseModel):
    """Pointer to a compile-check sidecar log per renderer target.

    Top-level peer of ``artefacts`` (ADR-025 Fork 2): compile-checks
    sidecars are evaluation outputs, not pipeline artefacts.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Aggregate classes — small typed rollups tightly coupled to one run
# (ADR-022 Fork 2). Standalone ``BaseModel`` per ADR-025 canonical.
# ---------------------------------------------------------------------------


class CacheStats(BaseModel):
    """Per-LLM-pass cache behaviour rollup.

    v1 shape is ``{calls, hits, hit_rate}`` only (ADR-025 Fork 5). The
    cost-estimate fields (``saved_usd_est``, ``incurred_usd_est``) require
    a cost model (a per-model price table) that v1 does not implement;
    including them would ship numbers that are always ``0.0``. They are
    re-added as an **additive ``2.x`` minor bump** when a cost model is
    introduced. Keyed by pass name (``"pass_1"``, ``"pass_2"``) at the
    ``Manifest.cache_stats`` level.
    """

    model_config = ConfigDict(extra="forbid")

    calls: int
    hits: int
    hit_rate: float
    # saved_usd_est / incurred_usd_est deferred until a cost model exists (ADR-025 Fork 5)


# ---------------------------------------------------------------------------
# Top-level manifest
# ---------------------------------------------------------------------------


class Manifest(BaseModel):
    """Top-level run manifest (manifest ``2.0.0``, flat layout — ADR-025).

    Fields grouped by ADR-022 Fork 2 category:

    * **Scalar metadata** — single primitive values describing the run as
      a whole (``schema_version``, ``codeograph_version``, ``source_path``,
      ``corpus_id``, ``run_id``, ``llm_skipped``).
    * **Aggregate metadata** — small typed rollups tightly coupled to
      this run (``cache_stats`` keyed by pass name).
    * **Payload pointers** — references to files that grow with the
      corpus or are independently consumed. Three top-level peers per
      ADR-025 Fork 2: ``artefacts`` (pipeline outputs), ``scorecards``
      and ``compile_checks`` (evaluation outputs).
    """

    model_config = ConfigDict(extra="forbid")

    # --- scalar metadata ---
    schema_version: str  # "2.0.0" (ADR-025)
    codeograph_version: str
    source_path: str
    corpus_id: str
    run_id: str = Field(pattern=RUN_ID_PATTERN)  # required in 2.0.0 (ADR-025 Invariants)
    llm_skipped: bool = False  # ADR-025 Fork 3

    # --- aggregate metadata ---
    cache_stats: dict[str, CacheStats] | None = None  # keyed by pass name, e.g. "pass_1"

    # --- payload pointers (top-level peers; ADR-025 Fork 2) ---
    artefacts: dict[str, ArtefactPointer] = Field(default_factory=dict)
    scorecards: dict[str, ScorecardPointer] | None = None
    compile_checks: dict[str, CompileChecksPointer] | None = None


__all__ = [
    "ArtefactPointer",
    "CacheStats",
    "CompileChecksPointer",
    "Manifest",
    "ScorecardPointer",
]
