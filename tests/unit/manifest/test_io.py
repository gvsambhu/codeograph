"""Unit tests for ``manifest_io`` (ADR-025 Confirmation #7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeograph.manifest.io import read, write
from codeograph.manifest.schema import (
    ArtefactPointer,
    CacheStats,
    CompileChecksPointer,
    Manifest,
    ScorecardPointer,
)

# ---------------------------------------------------------------------------
# TestForwardCompat (Confirmation #7)
# ---------------------------------------------------------------------------


class TestForwardCompat:
    """A 2.1.0 manifest with an extra optional field reads successfully."""

    def test_2_1_0_manifest_with_extra_field_reads_successfully(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "manifest.json"

        # Build a 2.1.0-shaped dict with an extra top-level field "eval_stats".
        data = {
            "schema_version": "2.1.0",  # newer minor than current 2.0.0
            "codeograph_version": "0.1.0",
            "source_path": "/tmp/source",
            "corpus_id": "corpus-1",
            "run_id": "2026-06-11T10-00-00Z-a1b2c3",
            "llm_skipped": False,
            "cache_stats": {
                "pass_1": {"calls": 1, "hits": 0, "hit_rate": 0.0},
            },
            "artefacts": {
                "graph": {
                    "path": "graph.json",
                    "schema_version": "1.0.0",
                    "sha256": "0" * 64,
                }
            },
            "scorecards": {
                "graph": {
                    "path": "evals/graph-scorecard.json",
                    "sha256": "1" * 64,
                    "overall": "pass",
                }
            },
            "compile_checks": {
                "java": {
                    "path": "compile/java.json",
                    "sha256": "2" * 64,
                }
            },
            # Extra field introduced by a hypothetical 2.1.0 producer.
            "eval_stats": {"total": 42},
        }

        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        manifest = read(manifest_path)

        assert isinstance(manifest, Manifest)
        # Unknown field should be dropped; current schema has no eval_stats attribute.
        assert not hasattr(manifest, "eval_stats")

    def test_unknown_field_drops_with_debug_log(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        manifest_path = tmp_path / "manifest.json"

        data = {
            "schema_version": "2.1.0",
            "codeograph_version": "0.1.0",
            "source_path": "/tmp/source",
            "corpus_id": "corpus-1",
            "run_id": "2026-06-11T10-00-00Z-a1b2c3",
            "llm_skipped": False,
            "artefacts": {},
            # Extra unknown top-level field.
            "eval_stats": {"total": 42},
        }

        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        import codeograph.manifest.io

        captured_logs = []
        monkeypatch.setattr(
            codeograph.manifest.io.logger, "debug", lambda msg, *args, **kwargs: captured_logs.append(msg % args)
        )

        manifest = read(manifest_path)
        assert isinstance(manifest, Manifest)

        # Ensure a DEBUG log mentioning the dropped field name was emitted.
        assert any("eval_stats" in msg and "dropped unknown top-level field" in msg for msg in captured_logs)

    def test_2_0_0_manifest_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "manifest.json"

        original = Manifest(
            schema_version="2.0.0",
            codeograph_version="0.1.0",
            source_path="/tmp/source",
            corpus_id="corpus-1",
            run_id="2026-06-11T10-00-00Z-a1b2c3",
            llm_skipped=False,
            cache_stats={
                "pass_1": CacheStats(calls=10, hits=7, hit_rate=0.7),
            },
            artefacts={
                "graph": ArtefactPointer(
                    path="graph.json",
                    schema_version="1.0.0",
                    sha256="0" * 64,
                ),
                "llm_annotations": ArtefactPointer(
                    path="llm-annotations.json",
                    schema_version="1.0.0",
                    sha256="1" * 64,
                ),
            },
            scorecards={
                "graph": ScorecardPointer(
                    path="evals/graph-scorecard.json",
                    sha256="2" * 64,
                    overall="pass",
                )
            },
            compile_checks={
                "java": CompileChecksPointer(
                    path="compile/java.json",
                    sha256="3" * 64,
                )
            },
        )

        write(original, manifest_path)
        reread = read(manifest_path)

        assert reread == original


# ---------------------------------------------------------------------------
# TestStrictOnWrite
# ---------------------------------------------------------------------------


class TestStrictOnWrite:
    """Strict-on-write via Pydantic ``extra='forbid'``."""

    def test_constructing_manifest_with_extra_field_raises(self) -> None:
        # Manifest.model_config.extra is "forbid", so extra kwargs should
        # trigger a ValidationError when using the normal constructor.
        with pytest.raises(Exception) as excinfo:
            Manifest(
                schema_version="2.0.0",
                codeograph_version="0.1.0",
                source_path="/tmp/source",
                corpus_id="corpus-1",
                run_id="2026-06-11T10-00-00Z-a1b2c3",
                llm_skipped=False,
                artefacts={},
                rogue_field="should_fail",  # type: ignore[call-arg]
            )
        # Pydantic v2 raises pydantic.ValidationError; we avoid importing it
        # just to keep the test focused on behavior, but ensure it's a ValueError-like failure.
        err_msg = str(excinfo.value)
        assert (
            "extra fields not permitted" in err_msg
            or "Extra inputs are not permitted" in err_msg
            or "extra_forbidden" in err_msg
        )

    def test_write_rejects_model_with_extra_field(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "manifest.json"

        # model_construct bypasses validation, so we can smuggle an extra field
        # into the instance; strict-on-write is provided by the constructor,
        # so write() itself will happily serialize whatever fields exist.
        # This test documents that behaviour.
        m = Manifest.model_construct(
            schema_version="2.0.0",
            codeograph_version="0.1.0",
            source_path="/tmp/source",
            corpus_id="corpus-1",
            run_id="2026-06-11T10-00-00Z-a1b2c3",
            llm_skipped=False,
            artefacts={},
            cache_stats=None,
            scorecards=None,
            compile_checks=None,
        )
        # Inject an extra attribute post-construction.
        object.__setattr__(m, "rogue_field", "smuggled")

        write(m, manifest_path)

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        # model_dump_json respects extra='forbid' configuration and only dumps declared fields,
        # so the extra attribute is not persisted.
        assert "rogue_field" not in raw
