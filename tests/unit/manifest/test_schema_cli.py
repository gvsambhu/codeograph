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

import json
import subprocess
import sys
from pathlib import Path

import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# TestFreshnessGate (Confirmation #8)
# ---------------------------------------------------------------------------


class TestFreshnessGate:
    """``--check`` exits 0 on a clean tree; non-zero on drift."""

    def test_check_exits_0_on_clean_tree(self) -> None:
        res = subprocess.run(
            [sys.executable, "-m", "codeograph.manifest.schema_cli", "--check"],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0

    def test_check_exits_nonzero_when_schema_stale(self, tmp_path: Path) -> None:
        target = tmp_path / "manifest.schema.json"
        target.write_text("{}", encoding="utf-8")
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "codeograph.manifest.schema_cli",
                "--check",
                "--schema-path",
                str(target),
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0
        assert "stale" in res.stderr

    def test_generate_writes_matching_schema(self, tmp_path: Path) -> None:
        from codeograph.manifest.schema_cli import GENERATED_SCHEMA_PATH

        target = tmp_path / "manifest.schema.json"
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "codeograph.manifest.schema_cli",
                "--generate",
                "--schema-path",
                str(target),
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        generated = json.loads(target.read_text(encoding="utf-8"))
        committed = json.loads(GENERATED_SCHEMA_PATH.read_text(encoding="utf-8"))
        assert generated == committed


# ---------------------------------------------------------------------------
# TestCommittedSchema
# ---------------------------------------------------------------------------


class TestCommittedSchema:
    """Properties of the committed ``_generated/manifest.schema.json``."""

    def test_schema_declares_draft_2020_12(self) -> None:
        from codeograph.manifest.schema_cli import GENERATED_SCHEMA_PATH

        schema_data = json.loads(GENERATED_SCHEMA_PATH.read_text(encoding="utf-8"))
        assert schema_data.get("$schema") == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_contains_required_top_level_fields(self) -> None:
        from codeograph.manifest.schema_cli import GENERATED_SCHEMA_PATH

        schema_data = json.loads(GENERATED_SCHEMA_PATH.read_text(encoding="utf-8"))
        required_fields = schema_data.get("required", [])

        expected_required = [
            "schema_version",
            "codeograph_version",
            "source_path",
            "corpus_id",
            "run_id",
        ]
        for field in expected_required:
            assert field in required_fields

        assert "artefacts" in schema_data.get("properties", {})
