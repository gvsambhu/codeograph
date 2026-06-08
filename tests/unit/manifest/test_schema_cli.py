"""Unit tests for the ``schema_cli --check`` freshness gate (ADR-025 Confirmation #8).

Scaffolding is AI-generated; the assertion bodies are learner-write per
the DC5 M12 spec.

Per ADR-025 §"Confirmation":
* 8 — ``python -m codeograph.manifest.schema_cli --check`` exits 0 on a
      clean tree and non-zero when the Pydantic source changes without
      regenerating ``codeograph/_generated/manifest.schema.json``; the
      committed schema declares ``$schema: 2020-12``.
"""
from __future__ import annotations

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import json  # noqa: F401
import subprocess  # noqa: F401
import sys  # noqa: F401
from pathlib import Path  # noqa: F401

import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# TestFreshnessGate (Confirmation #8)
# ---------------------------------------------------------------------------


class TestFreshnessGate:
    """``--check`` exits 0 on a clean tree; non-zero on drift."""

    def test_check_exits_0_on_clean_tree(self) -> None:
        # TODO(learner): invoke `python -m codeograph.manifest.schema_cli
        # --check` as a subprocess; assert returncode == 0. (The
        # committed manifest.schema.json was regenerated in M4 to
        # match the current Pydantic source, so the check is green.)
        ...

    def test_check_exits_nonzero_when_schema_stale(self, tmp_path: Path) -> None:
        # TODO(learner): mutate the committed manifest.schema.json
        # (e.g. write "{}" over it), invoke --check, assert returncode
        # != 0; then restore the original. (This is the freshness-gate
        # failure scenario the CI lint job guards against.)
        ...

    def test_check_is_invokable_via_python_module(self) -> None:
        # TODO(learner): assert the CLI can be invoked as
        # `python -m codeograph.manifest.schema_cli --check` (proves
        # it's a proper Click module; the conftest auto-cd's to
        # repo root in subprocess calls; use absolute path to python).
        ...


# ---------------------------------------------------------------------------
# TestCommittedSchema
# ---------------------------------------------------------------------------


class TestCommittedSchema:
    """Properties of the committed ``_generated/manifest.schema.json``."""

    def test_schema_declares_draft_2020_12(self) -> None:
        # TODO(learner): read
        # codeograph/_generated/manifest.schema.json; assert the
        # ``$schema`` field equals
        # "https://json-schema.org/draft/2020-12/schema".
        ...

    def test_schema_contains_required_top_level_fields(self) -> None:
        # TODO(learner): assert the schema's "required" list includes
        # all five required scalars (schema_version, codeograph_version,
        # source_path, corpus_id, run_id) and that "artefacts" is
        # required too.
        ...
