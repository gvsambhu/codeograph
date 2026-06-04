"""Unit tests for codeograph/evals/runner.py (ADR-017 Forks 5+6)."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from codeograph.evals.runner import EvalRunner, MissingOutputError
from codeograph.evals.scorecard_schema import (
    BooleanThreshold,
    CheckResult,
    MinRatioThreshold,
    ScoreBandThreshold,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(out_dir: Path, corpus_id: str = "test-corpus") -> None:
    manifest = {
        "schema_version": "1.6.0",
        "codeograph_version": "0.1.0",
        "source_path": str(out_dir),
        "corpus_id": corpus_id,
        "artefacts": {
            "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
            "llm_annotations": {
                "path": "llm-annotations.json",
                "schema_version": "1.0.0",
                "sha256": None,
            },
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_empty_graph(out_dir: Path) -> None:
    graph = {"nodes": [], "edges": []}
    (out_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _make_pass_check(check_id: str, category: str = "graph") -> CheckResult:
    return CheckResult(
        id=check_id,
        category=category,
        value=True,
        threshold=BooleanThreshold(expected=True),
        rationale="test",
        duration_ms=1,
    )


def _make_skip_check(check_id: str, category: str = "graph") -> CheckResult:
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
    "codeograph.evals.runner.check_golden_graph_agreement":   lambda od: _make_pass_check("golden_graph_agreement"),
    "codeograph.evals.runner.check_internal_consistency":     lambda g: _make_pass_check("internal_consistency"),
    "codeograph.evals.runner.check_relationship_correctness": lambda g: _make_pass_check("relationship_correctness"),
    "codeograph.evals.runner.check_reproducibility":          lambda od: _make_skip_check("reproducibility"),
    "codeograph.evals.runner.check_schema_validity":          lambda g: _make_pass_check("schema_validity"),
    "codeograph.evals.runner.check_semantic_accuracy":        lambda g: _make_skip_check("semantic_accuracy"),
    "codeograph.evals.runner.check_structural_completeness":  lambda g: _make_pass_check("structural_completeness"),
}

_CODE_CHECK_PATCHES = {
    "codeograph.evals.runner.check_compile":   lambda od, t: CheckResult(
        id="compile", category="code", value=1.0,
        threshold=MinRatioThreshold(pass_at_or_above=1.0), rationale="test", duration_ms=1,
    ),
    "codeograph.evals.runner.check_coverage":  lambda od, t: CheckResult(
        id="coverage", category="code", result="skip", value=None,
        threshold=MinRatioThreshold(pass_at_or_above=0.95, fail_below=0.85),
        rationale="test", duration_ms=0,
        details={"skip_reason": "no_v1_translatable_features_in_corpus"},
    ),
    "codeograph.evals.runner.check_llm_judge": lambda od, t: CheckResult(
        id="llm_judge", category="code", result="skip", value=None,
        threshold=ScoreBandThreshold(pass_at_or_above=None, fail_below=None),
        rationale="test", duration_ms=0,
        details={"skip_reason": "deferred_v1.1"},
    ),
}


# ---------------------------------------------------------------------------
# Preflight tests
# ---------------------------------------------------------------------------


def test_runner_raises_when_output_dir_missing(tmp_path: Path):
    runner = EvalRunner()
    with pytest.raises(MissingOutputError, match="no rendered output"):
        runner.run(tmp_path / "nonexistent", scorecard_kinds=["graph"])


def test_runner_raises_when_manifest_missing(tmp_path: Path):
    runner = EvalRunner()
    with pytest.raises(MissingOutputError):
        runner.run(tmp_path, scorecard_kinds=["graph"])


# ---------------------------------------------------------------------------
# Graph scorecard
# ---------------------------------------------------------------------------


def test_runner_produces_graph_scorecard(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = runner.run(tmp_path, scorecard_kinds=["graph"])

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

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        runner.run(tmp_path, scorecard_kinds=["graph"])

    scorecard_file = tmp_path / "evals" / "graph-scorecard.json"
    assert scorecard_file.exists()
    data = json.loads(scorecard_file.read_text(encoding="utf-8"))
    assert data["kind"] == "graph"


def test_manifest_scorecards_pointer_updated(tmp_path: Path):
    _write_manifest(tmp_path)
    _write_empty_graph(tmp_path)

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        runner.run(tmp_path, scorecard_kinds=["graph"])

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    scorecards_ptr = manifest["artefacts"]["scorecards"]
    assert "graph" in scorecards_ptr
    assert "path" in scorecards_ptr["graph"]
    assert "sha256" in scorecards_ptr["graph"]
    assert "overall" in scorecards_ptr["graph"]


# ---------------------------------------------------------------------------
# Code scorecard
# ---------------------------------------------------------------------------


def test_runner_skips_code_scorecard_when_target_not_rendered(tmp_path: Path):
    _write_manifest(tmp_path)
    runner = EvalRunner()
    scorecards = runner.run(tmp_path, scorecard_kinds=["ts"])
    assert len(scorecards) == 1
    sc = scorecards[0]
    assert sc.kind == "ts"
    assert all(c.result == "skip" for c in sc.checks)
    assert all(c.details.get("skip_reason") == "target_not_rendered" for c in sc.checks)


def test_runner_runs_code_checks_when_target_exists(tmp_path: Path):
    _write_manifest(tmp_path)
    (tmp_path / "ts").mkdir()

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _CODE_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = runner.run(tmp_path, scorecard_kinds=["ts"])

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

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = runner.run(
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

    runner = EvalRunner()
    with ExitStack() as stack:
        for name, fn in _GRAPH_CHECK_PATCHES.items():
            stack.enter_context(patch(name, side_effect=fn))
        scorecards = runner.run(
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
