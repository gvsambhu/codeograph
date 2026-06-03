"""Unit tests for codeograph/evals/checks/code/coverage.py (ADR-017 Fork 4)."""

from __future__ import annotations

import json
from pathlib import Path

from codeograph.evals.checks.code.coverage import check_coverage


def _write_manifest(out_dir: Path) -> None:
    manifest = {
        "schema_version": "1.6.0",
        "codeograph_version": "0.1.0",
        "source_path": str(out_dir),
        "corpus_id": "test-corpus",
        "artefacts": {
            "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
            "llm_annotations": {"path": "llm-annotations.json", "schema_version": "1.0.0", "sha256": None},
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_sidecar(out_dir: Path, groups: list[dict]) -> None:
    evals_dir = out_dir / "evals"
    evals_dir.mkdir(exist_ok=True)
    sidecar = {"schema_version": "1.0.0", "target": "ts", "groups": groups}
    (evals_dir / "coverage-data.ts.json").write_text(json.dumps(sidecar), encoding="utf-8")


# ---------------------------------------------------------------------------
# Skip paths
# ---------------------------------------------------------------------------


def test_coverage_skip_when_sidecar_missing(tmp_path: Path):
    """No coverage-data sidecar → skip with no_v1_translatable_features_in_corpus."""
    _write_manifest(tmp_path)
    result = check_coverage(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "no_v1_translatable_features_in_corpus"


def test_coverage_skip_when_all_groups_empty(tmp_path: Path):
    """Sidecar exists but total v1_translatable is zero → skip."""
    _write_manifest(tmp_path)
    _write_sidecar(tmp_path, [
        {"selected": [], "refused": [], "stub_todos": [], "feature_policies_active": []},
    ])
    result = check_coverage(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "no_v1_translatable_features_in_corpus"


# ---------------------------------------------------------------------------
# Pass / fail / band-gap paths
# ---------------------------------------------------------------------------


def test_coverage_pass_when_nothing_refused_or_stubbed(tmp_path: Path):
    """All 10 selected, none refused, none stub_todo → value=1.0, pass."""
    _write_manifest(tmp_path)
    _write_sidecar(tmp_path, [
        {
            "selected": [f"com.example.Class{i}" for i in range(10)],
            "refused": [],
            "stub_todos": [],
            "feature_policies_active": [],
        }
    ])
    result = check_coverage(tmp_path, "ts")
    assert result.result == "pass"
    assert result.value == 1.0


def test_coverage_fail_when_many_refused(tmp_path: Path):
    """6 selected, 4 refused → value=6/10=0.6, fail (below 0.85)."""
    _write_manifest(tmp_path)
    _write_sidecar(tmp_path, [
        {
            "selected": [f"com.example.S{i}" for i in range(6)],
            "refused": [f"com.example.R{i}" for i in range(4)],
            "stub_todos": [],
            "feature_policies_active": ["security_feature_policy"],
        }
    ])
    result = check_coverage(tmp_path, "ts")
    assert result.result == "fail"
    assert result.value < 0.85


def test_coverage_band_gap_when_partially_covered(tmp_path: Path):
    """9 selected, 1 refused, 1 stub_todo → value=8/10=0.80, band_gap skip."""
    _write_manifest(tmp_path)
    _write_sidecar(tmp_path, [
        {
            # 9 selected + 1 refused = 10 v1_translatable; 0 stub_todos
            # → v1_actually_emitted = 9; value = 9/10 = 0.9
            # 0.85 ≤ 0.9 < 0.95 → band_gap skip
            "selected": [f"com.example.S{i}" for i in range(9)],
            "refused": ["com.example.Refused"],
            "stub_todos": [],
            "feature_policies_active": [],
        }
    ])
    result = check_coverage(tmp_path, "ts")
    # 9/10 = 0.9 → in band gap (0.85 ≤ value < 0.95) → skip
    assert result.result == "skip"
    assert result.details["skip_reason"] == "band_gap"


def test_coverage_aggregates_across_multiple_groups(tmp_path: Path):
    """Two domain groups: totals are summed before computing ratio."""
    _write_manifest(tmp_path)
    _write_sidecar(tmp_path, [
        {"selected": ["A", "B", "C"], "refused": [], "stub_todos": [], "feature_policies_active": []},
        {"selected": ["D", "E"], "refused": ["F"], "stub_todos": [], "feature_policies_active": []},
    ])
    # selected=5, refused=1 → v1_translatable=6, v1_emitted=5 → 5/6≈0.833 → band_gap
    result = check_coverage(tmp_path, "ts")
    assert result.details["v1_translatable"] == 6
    assert result.details["v1_actually_emitted"] == 5
