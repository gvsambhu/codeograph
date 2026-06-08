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

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import pytest  # noqa: F401

from codeograph.manifest.schema import (  # noqa: F401
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
        # TODO(learner): build an ArtefactPointer with sha256=None and
        # assert that pydantic.ValidationError is raised.
        ...

    def test_artefact_pointer_rejects_non_64_hex_sha256(self) -> None:
        # TODO(learner): build an ArtefactPointer with sha256="not-hex"
        # (or any non-64-hex string) and assert ValidationError.
        ...

    def test_scorecard_pointer_rejects_null_sha256(self) -> None:
        # TODO(learner): same as the artefact case but for ScorecardPointer.
        ...

    @pytest.mark.parametrize(
        "bad_sha",
        [
            "a" * 63,            # too short by 1
            "a" * 65,            # too long by 1
            "g" * 64,            # non-hex char
            "A" * 64,            # uppercase (regex is lowercase-only)
            " " * 64,            # spaces
        ],
    )
    def test_artefact_pointer_rejects_malformed_sha256(self, bad_sha: str) -> None:
        # TODO(learner): build an ArtefactPointer with sha256=bad_sha and
        # assert ValidationError for each parametrize case.
        ...


# ---------------------------------------------------------------------------
# TestArtefactSchemaVersion (Confirmation #5)
# ---------------------------------------------------------------------------


class TestArtefactSchemaVersion:
    """ADR-025 Confirmation #5: ``artefacts.graph.schema_version`` is
    present and is a string (per-artefact version retained per Fork 4)."""

    def test_artefact_pointer_schema_version_is_string(self) -> None:
        ptr = _valid_graph_pointer()  # noqa: F841 — used by learner assertion
        # TODO(learner): assert isinstance(ptr.schema_version, str) and
        # assert len(ptr.schema_version) > 0.
        ...

    def test_manifest_round_trip_preserves_per_artefact_version(self) -> None:
        # TODO(learner): build a Manifest with an ArtefactPointer carrying
        # schema_version="1.2.3", model_dump_json, re-parse, and assert
        # the per-artefact schema_version survives.
        ...


# ---------------------------------------------------------------------------
# TestCacheStatsNoCostFields (Confirmation #6)
# ---------------------------------------------------------------------------


class TestCacheStatsNoCostFields:
    """ADR-025 Confirmation #6: ``CacheStats`` carrying ``saved_usd_est`` or
    ``incurred_usd_est`` raises ``ValidationError`` (cost fields absent in
    v1; re-added as an additive 2.x bump when a cost model lands)."""

    def test_cache_stats_rejects_saved_usd_est(self) -> None:
        # TODO(learner): build a CacheStats via model_construct with
        # saved_usd_est=0.5 (bypassing the field mask) and assert that
        # extra="forbid" rejects it. (Hint: pydantic v2 uses
        # model_construct + _fields_set; or try setattr.)
        ...

    def test_cache_stats_rejects_incurred_usd_est(self) -> None:
        # TODO(learner): same as above but for incurred_usd_est.
        ...

    def test_cache_stats_v1_shape_is_three_fields(self) -> None:
        # TODO(learner): build a CacheStats with the 3 v1 fields
        # (calls, hits, hit_rate) and assert it validates; assert
        # sorted(model_fields) == ["calls", "hit_rate", "hits"].
        ...


# ---------------------------------------------------------------------------
# TestRunIdRequired (Confirmation #9)
# ---------------------------------------------------------------------------


class TestRunIdRequired:
    """ADR-025 Confirmation #9: Manifest without ``run_id``, or with
    ``run_id: null``, raises ``ValidationError`` (``run_id`` is a required
    scalar in 2.0.0)."""

    def test_manifest_rejects_missing_run_id(self) -> None:
        # TODO(learner): try to build a Manifest via model_construct with
        # run_id missing (bypass required-field check) and assert
        # ValidationError when model_validate_json is called. Or use
        # model_construct and then call model_dump + model_validate to
        # trigger strict validation.
        ...

    def test_manifest_with_null_run_id_raises(self) -> None:
        # TODO(learner): Manifest(run_id=None, ...) should fail because
        # run_id is required and str (not Optional[str]).
        ...

    def test_manifest_with_empty_run_id_raises(self) -> None:
        # TODO(learner): Manifest(run_id="", ...) should fail because
        # the regex pattern from RUN_ID_PATTERN rejects empty strings.
        # Use generate_run_id()'s RUN_ID_PATTERN as the source of truth.
        ...
