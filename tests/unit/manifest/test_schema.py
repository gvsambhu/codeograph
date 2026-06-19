"""Unit tests for the 2.0.0 manifest Pydantic schema (ADR-025 Confirmations 3, 5, 6, 9).

Scaffolding is AI-generated; the assertion bodies are learner-write per the
DC5 M12 spec. Each test has a ``# TODO(learner):`` marker naming the
ADR-025 Confirmation item it implements.

Per ADR-025 §"Confirmation":
* 3 — Manifest with any pointer whose ``sha256`` is ``null`` or non-64-hex
      raises ``ValidationError``.
* 5 — ``artefacts.graph.schema_version`` is present and is a string.
* 6 — ``CacheStats`` carrying ``saved_usd_est`` or ``incurred_usd_est``
      raises ``ValidationError`` (``extra="forbid"``).
* 9 — Manifest without ``run_id``, or with ``run_id: null``, raises
      ``ValidationError``.
"""

from __future__ import annotations

import pydantic

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import pytest  # noqa: F401

from codeograph.manifest.models import (  # noqa: F401
    ArtefactPointer,
    CacheStats,
    Manifest,
    ScorecardPointer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_graph_pointer() -> ArtefactPointer:
    """A conformant ``ArtefactPointer`` for use as a fixture building block."""
    return ArtefactPointer(
        path="graph.json",
        schema_version="1.0.0",
        sha256="a" * 64,
    )


# ---------------------------------------------------------------------------
# TestSha256Required (Confirmation #3)
# ---------------------------------------------------------------------------


class TestSha256Required:
    """ADR-025 Confirmation #3: ``sha256`` is required and 64-hex on every
    present pointer."""

    def test_artefact_pointer_rejects_null_sha256(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            # Pass None for the required sha256 string field
            ArtefactPointer(
                path="graph.json",
                schema_version="1.0.0",
                sha256=None,  # type: ignore[arg-type]
            )

    def test_artefact_pointer_rejects_non_64_hex_sha256(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            ArtefactPointer(
                path="graph.json",
                schema_version="1.0.0",
                sha256="not-hex-at-all",
            )

    def test_scorecard_pointer_rejects_null_sha256(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            ScorecardPointer(
                path="scorecard.json",
                sha256=None,  # type: ignore[arg-type]
                overall="pass",
            )

    @pytest.mark.parametrize(
        "bad_sha",
        [
            "a" * 63,  # too short by 1
            "a" * 65,  # too long by 1
            "g" * 64,  # non-hex char
            "A" * 64,  # uppercase (regex is lowercase-only)
            " " * 64,  # spaces
        ],
    )
    def test_artefact_pointer_rejects_malformed_sha256(self, bad_sha: str) -> None:
        with pytest.raises(pydantic.ValidationError):
            ArtefactPointer(
                path="graph.json",
                schema_version="1.0.0",
                sha256=bad_sha,
            )


# ---------------------------------------------------------------------------
# TestArtefactSchemaVersion (Confirmation #5)
# ---------------------------------------------------------------------------


class TestArtefactSchemaVersion:
    """ADR-025 Confirmation #5: ``artefacts.graph.schema_version`` is
    present and is a string (per-artefact version retained per Fork 4)."""

    def test_artefact_pointer_schema_version_is_string(self) -> None:
        ptr = _valid_graph_pointer()
        assert isinstance(ptr.schema_version, str)
        assert len(ptr.schema_version) > 0

    def test_manifest_round_trip_preserves_per_artefact_version(self) -> None:
        ptr = ArtefactPointer(path="graph.json", schema_version="1.2.3", sha256="a" * 64)
        m = Manifest(
            schema_version="2.0.0",
            codeograph_version="0.1.0",
            source_path=".",
            corpus_id="test",
            run_id="2026-06-09T12-00-00Z-abcdef",
            artefacts={"graph": ptr},
        )

        # Round-trip serialize and validate
        dumped = m.model_dump_json()
        loaded = Manifest.model_validate_json(dumped)

        # Verify the version on the artefact pointer was preserved
        assert loaded.artefacts["graph"].schema_version == "1.2.3"


# ---------------------------------------------------------------------------
# TestCacheStatsNoCostFields (Confirmation #6)
# ---------------------------------------------------------------------------


class TestCacheStatsNoCostFields:
    """ADR-025 Confirmation #6: ``CacheStats`` carrying ``saved_usd_est`` or
    ``incurred_usd_est`` raises ``ValidationError`` (cost fields absent in
    v1; re-added as an additive 2.x bump when a cost model lands)."""

    def test_cache_stats_rejects_saved_usd_est(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            CacheStats.model_validate(
                {
                    "calls": 1,
                    "hits": 1,
                    "hit_rate": 1.0,
                    "saved_usd_est": 0.5,
                }
            )

    def test_cache_stats_rejects_incurred_usd_est(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            CacheStats.model_validate(
                {
                    "calls": 1,
                    "hits": 1,
                    "hit_rate": 1.0,
                    "incurred_usd_est": 0.5,
                }
            )

    def test_cache_stats_v1_shape_is_three_fields(self) -> None:
        # Verify that constructing it with exactly the 3 v1 fields is valid
        stats = CacheStats(calls=10, hits=8, hit_rate=0.8)
        assert stats.calls == 10
        assert stats.hits == 8
        assert stats.hit_rate == 0.8

        # Verify no cost fields exist in the schema
        assert "saved_usd_est" not in stats.model_fields
        assert "incurred_usd_est" not in stats.model_fields


# ---------------------------------------------------------------------------
# TestRunIdRequired (Confirmation #9)
# ---------------------------------------------------------------------------


class TestRunIdRequired:
    """ADR-025 Confirmation #9: Manifest without ``run_id``, or with
    ``run_id: null``, raises ``ValidationError`` (``run_id`` is a required
    scalar in 2.0.0)."""

    def test_manifest_rejects_missing_run_id(self) -> None:
        raw_missing_run_id = {
            "schema_version": "2.0.0",
            "codeograph_version": "0.1.0",
            "source_path": ".",
            "corpus_id": "test",
            # run_id is missing
            "artefacts": {},
        }
        with pytest.raises(pydantic.ValidationError):
            Manifest.model_validate(raw_missing_run_id)

    def test_manifest_with_null_run_id_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Manifest(
                schema_version="2.0.0",
                codeograph_version="0.1.0",
                source_path=".",
                corpus_id="test",
                run_id=None,  # type: ignore[arg-type]
                artefacts={},
            )

    def test_manifest_with_empty_run_id_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Manifest(
                schema_version="2.0.0",
                codeograph_version="0.1.0",
                source_path=".",
                corpus_id="test",
                run_id="",
                artefacts={},
            )
