"""Unit tests for codeograph/evals/runner.py (ADR-017 Forks 5+6)."""

from __future__ import annotations

import json
import re
from contextlib import ExitStack
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from codeograph.evals.models import (
    BooleanThreshold,
    CheckResult,
    MinRatioThreshold,
    ScoreBandThreshold,
)
from codeograph.evals.runner import MissingOutputError, run_evals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(out_dir: Path, corpus_id: str = "test-corpus") -> None:
    """Write a 2.0.0 manifest (flat layout, top-level scorecards)."""
    manifest = {
        "schema_version": "2.0.0",
        "codeograph_version": "0.1.0",
        "source_path": str(out_dir),
        "corpus_id": corpus_id,
        "run_id": "2026-06-08T00-00-00Z-000000",
        "llm_skipped": False,
        "artefacts": {
            "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
            "llm_annotations": {
                "path": "llm-annotations.json",
                "schema_version": "1.0.0",
                "sha256": "a" * 64,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8", newline="")


def _write_empty_graph(out_dir: Path) -> None:
    graph: dict[str, list[object]] = {"nodes": [], "edges": []}
    (out_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _make_pass_check(check_id: str, category: Literal["graph", "code"] = "graph") -> CheckResult:
    return CheckResult(
        id=check_id,
        category=category,
        value=True,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=1,
    )


def _make_skip_check(check_id: str, category: Literal["graph", "code"] = "graph") -> CheckResult:
    return CheckResult(
        id=check_id,
        category=category,
        result="skip",
        value=None,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=0,
        details={"skip_reason": "deferred_v1.1"},
    )


# Patch target for all graph checks (they're imported into runner namespace)
_GRAPH_CHECK_PATCHES = {
    "codeograph.evals.runner.check_golden_graph_agreement": lambda od: _make_pass_check("golden_graph_agreement"),
    "codeograph.evals.runner.check_internal_consistency": lambda g: _make_pass_check("internal_consistency"),
    "codeograph.evals.runner.check_relationship_correctness": lambda g: _make_pass_check("relationship_correctness"),
    "codeograph.evals.runner.check_reproducibility": lambda od: _make_skip_check("reproducibility"),
    "codeograph.evals.runner.check_schema_validity": lambda g: _make_pass_check("schema_validity"),
    "codeograph.evals.runner.check_semantic_accuracy": lambda g: _make_skip_check("semantic_accuracy"),
    "codeograph.evals.runner.check_structural_completeness": lambda g: _make_pass_check("structural_completeness"),
}

_CODE_CHECK_PATCHES = {
    "codeograph.evals.runner.check_compile": lambda od, t: CheckResult(
        id="compile",
        category="code",
        value=1.0,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale="test",
        duration_ms=1,
    ),
    "codeograph.evals.runner.check_coverage": lambda od, t: CheckResult(
        id="coverage",
        category="code",
        result="skip",
        value=None,
        threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
        rationale="test",
        duration_ms=0,
        details={"skip_reason": "no_v1_translatable_features_in_corpus"},
    ),
    "codeograph.evals.runner.check_llm_judge": lambda od, t: CheckResult(
        id="llm_judge",
        category="code",
        result="skip",
        value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="test",
        duration_ms=0,
        details={"skip_reason": "deferred_v1.1"},
    ),
}


# ---------------------------------------------------------------------------
# Preflight tests
# ---------------------------------------------------------------------------


def test_runner_raises_when_output_dir_missing(tmp_path: Path):
    with pytest.raises(MissingOutputError, match="no rendered output"):
        run_evals(tmp_path / "nonexistent", scorecard_kinds=["graph"])


def test_runner_raises_when_manifest_missing(tmp_path: Path):
    with pytest.raises(MissingOutputError):
        run_evals(tmp_path, scorecard_kinds=["graph"])


# ---------------------------------------------------------------------------
# Graph scorecard
# ---------------------------------------------------------------------------


def test_runner_produces_graph_scorecard(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = run_evals(tmp_path, scorecard_kinds=["graph"])

    assert len(scorecards) == 1
    sc = scorecards[0]
    assert sc.kind == "graph"
    assert len(sc.checks) == 7
    check_ids = {c.id for c in sc.checks}
    assert "structural_completeness" in check_ids
    assert "semantic_accuracy" in check_ids


def test_graph_scorecard_written_to_disk(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        run_evals(tmp_path, scorecard_kinds=["graph"])

    scorecard_file = tmp_path / "evals" / "graph-scorecard.json"
    assert scorecard_file.exists()
    data = json.loads(scorecard_file.read_text(encoding="utf-8"))
    assert data["kind"] == "graph"


def test_manifest_scorecards_pointer_updated(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        run_evals(tmp_path, scorecard_kinds=["graph"])

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    # 2.0.0: scorecards is TOP-LEVEL, not nested under artefacts (ADR-025 Fork 2)
    assert "artefacts" in manifest  # graph + llm_annotations still nested
    assert "scorecards" in manifest  # top-level in 2.0.0
    assert "scorecards" not in manifest["artefacts"]
    scorecards_ptr = manifest["scorecards"]
    assert "graph" in scorecards_ptr
    assert "path" in scorecards_ptr["graph"]
    assert "sha256" in scorecards_ptr["graph"]
    assert "overall" in scorecards_ptr["graph"]


def test_manifest_scorecards_pointer_is_valid_against_schema(tmp_path: Path):
    """The written scorecards pointer satisfies the 2.0.0 schema invariants.

    Per ADR-025 Invariants: sha256 is required and 64-hex; overall must
    match the ``pass|fail|skip|mixed`` regex; the path follows the
    canonical ``evals/{kind}-scorecard.json`` form.
    """
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        run_evals(tmp_path, scorecard_kinds=["graph"])

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    sc = manifest["scorecards"]["graph"]
    assert re.fullmatch(r"^[0-9a-f]{64}$", sc["sha256"]), f"sha256 {sc['sha256']!r} is not 64-hex"
    assert re.fullmatch(r"^(pass|fail|skip|mixed)$", sc["overall"]), (
        f"overall {sc['overall']!r} is not in the pass|fail|skip|mixed set"
    )
    assert sc["path"] == "evals/graph-scorecard.json"


# ---------------------------------------------------------------------------
# Code scorecard
# ---------------------------------------------------------------------------


def test_runner_skips_code_scorecard_when_target_not_rendered(tmp_path: Path):
    _write_manifest(tmp_path)
    scorecards = run_evals(tmp_path, scorecard_kinds=["ts"])
    assert len(scorecards) == 1
    sc = scorecards[0]
    assert sc.kind == "ts"
    assert all(c.result == "skip" for c in sc.checks)
    assert all(c.details.get("skip_reason") == "target_not_rendered" for c in sc.checks)


def test_runner_runs_code_checks_when_target_exists(tmp_path: Path):
    _write_manifest(tmp_path)
    (tmp_path / "ts").mkdir()

    with ExitStack() as stack:
        for name, fn in _CODE_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = run_evals(tmp_path, scorecard_kinds=["ts"])

    assert len(scorecards) == 1
    sc = scorecards[0]
    assert sc.kind == "ts"
    compile_check = next(c for c in sc.checks if c.id == "compile")
    assert compile_check.result == "pass"


# ---------------------------------------------------------------------------
# check_filter and skip_checks
# ---------------------------------------------------------------------------


def test_skip_checks_excludes_named_check(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = run_evals(
            tmp_path,
            scorecard_kinds=["graph"],
            skip_checks=["reproducibility"],
        )

    repro = next(c for c in scorecards[0].checks if c.id == "reproducibility")
    assert repro.result == "skip"
    assert repro.details.get("skip_reason") == "explicit_skip"


def test_check_filter_runs_only_named_checks(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = run_evals(
            tmp_path,
            scorecard_kinds=["graph"],
            check_filter=["structural_completeness"],
        )

    checks = scorecards[0].checks
    structural = next(c for c in checks if c.id == "structural_completeness")
    assert structural.result == "pass"

    # All others must be explicit_skip
    others = [c for c in checks if c.id != "structural_completeness"]
    assert all(c.details.get("skip_reason") == "explicit_skip" for c in others)
