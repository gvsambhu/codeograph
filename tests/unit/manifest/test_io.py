"""Unit tests for ``manifest_io`` (ADR-025 Confirmation #7).

Scaffolding is AI-generated; the assertion bodies are learner-write per
the DC5 M12 spec.

Per ADR-025 §"Confirmation":
* 7 — A manifest written by a hypothetical ``2.1.0`` producer with one
      added optional field is read successfully by the current reader,
      the unknown field handled per the forward-compat rule —
      additive ``2.x`` evolution holds.

The forward-compat rule (codified in ``manifest.io.read``): unknown
top-level fields are dropped with a DEBUG log; the remaining fields
validate against the current Pydantic schema.
"""
from __future__ import annotations

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import json  # noqa: F401
import logging  # noqa: F401
from pathlib import Path  # noqa: F401

import pytest  # noqa: F401

from codeograph.manifest.io import read, write  # noqa: F401
from codeograph.manifest.schema import Manifest  # noqa: F401

# ---------------------------------------------------------------------------
# TestForwardCompat (Confirmation #7)
# ---------------------------------------------------------------------------


class TestForwardCompat:
    """A 2.1.0 manifest with an extra optional field reads successfully."""

    def test_2_1_0_manifest_with_extra_field_reads_successfully(self, tmp_path: Path) -> None:
        # TODO(learner): write a 2.1.0-shaped manifest JSON that includes
        # an extra top-level field (e.g. "eval_stats": {...}) beyond the
        # 2.0.0 schema. Call read() and assert it returns a Manifest
        # (the extra field is dropped via lenient-on-read).
        # Build the 2.1.0 dict inline:
        # {
        #   "schema_version": "2.1.0",
        #   "codeograph_version": "0.1.0",
        #   ...all the 2.0.0 fields...
        #   "eval_stats": {"total": 42},  # the extra field
        # }
        ...

    def test_unknown_field_drops_with_debug_log(self, tmp_path: Path, caplog) -> None:
        # TODO(learner): write a manifest with an extra top-level field;
        # call read(); assert caplog.records contains a DEBUG record
        # mentioning the dropped field name. (The lenient-on-read path
        # in manifest.io.read emits a DEBUG log per dropped field.)
        ...

    def test_2_0_0_manifest_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        # TODO(learner): write a 2.0.0 manifest with all 9 top-level
        # keys (schema_version, codeograph_version, source_path,
        # corpus_id, run_id, llm_skipped, cache_stats, artefacts,
        # scorecards); call write(); call read(); assert the re-read
        # Manifest equals the original.
        ...


# ---------------------------------------------------------------------------
# TestStrictOnWrite
# ---------------------------------------------------------------------------


class TestStrictOnWrite:
    """Strict-on-write via Pydantic ``extra='forbid'``."""

    def test_constructing_manifest_with_extra_field_raises(self) -> None:
        # TODO(learner): try to construct a Manifest via the Pydantic
        # constructor with an extra kwarg (e.g. ``rogue_field=...``).
        # Assert ValidationError is raised.
        ...

    def test_write_rejects_model_with_extra_field(self, tmp_path: Path) -> None:
        # TODO(learner): construct a Manifest via model_construct with
        # an extra field, then call manifest_io.write. Assert either
        # (a) model_construct allows it but write raises, or
        # (b) the strict-on-write path catches it. Document which.
        ...
