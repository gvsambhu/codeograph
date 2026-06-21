"""Tests for ClassSelector and SelectionResult (M4 — ADR-009).

Strategy coverage:
  - take_all    : n ≤ cap
  - top_n_v1   : cap < n < 2*cap
  - stratified_threshold_v1 : n ≥ 2*cap

Threshold reference: Lanza & Marinescu (2006) pp 16-18.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers — build minimal ClassNode-like objects via the real Pydantic model
# ---------------------------------------------------------------------------
from codeograph.graph.models.graph_schema import ClassNode, CodeographKnowledgeGraph, Node
from codeograph.rendering.class_selector import (
    _HIGH_CBO_THRESHOLD,
    _HIGH_WMC_THRESHOLD,
    ClassSelector,
)
from codeograph.rendering.models import SelectionResult


def _make_class_node(
    fqcn: str,
    *,
    cbo: int | None = None,
    wmc: int | None = None,
    extraction_mode: str = "ast",
) -> ClassNode:
    """Build a minimal ClassNode with the given complexity metrics."""
    return ClassNode(
        id=fqcn,
        kind="class",
        name=fqcn.rsplit(".", 1)[-1],
        modifiers=["public"],
        source_file=f"src/main/java/{fqcn.replace('.', '/')}.java",
        line_range=[1, 50],
        extraction_mode=extraction_mode,
        cbo=cbo,
        wmc=wmc,
    )


def _make_graph(class_nodes: list[ClassNode]) -> CodeographKnowledgeGraph:
    """Wrap ClassNode list in a minimal CodeographKnowledgeGraph."""
    return CodeographKnowledgeGraph(
        nodes=[Node(root=cn) for cn in class_nodes],
        edges=[],
    )


# ---------------------------------------------------------------------------
# take_all tier (n ≤ cap)
# ---------------------------------------------------------------------------


class TestTakeAll:
    def test_small_group_selects_all(self):
        nodes = [_make_class_node(f"com.example.orders.Class{i}", wmc=i, cbo=0) for i in range(5)]
        graph = _make_graph(nodes)
        selector = ClassSelector(cap=10)
        results = selector.select(graph)

        assert len(results) == 1
        result = results[0]
        assert result.strategy == "take_all"
        assert len(result.selected) == 5
        assert len(result.excluded) == 0

    def test_exactly_cap_selects_all(self):
        nodes = [_make_class_node(f"com.example.orders.C{i}", wmc=1, cbo=0) for i in range(10)]
        graph = _make_graph(nodes)
        selector = ClassSelector(cap=10)
        results = selector.select(graph)
        assert results[0].strategy == "take_all"
        assert len(results[0].selected) == 10


# ---------------------------------------------------------------------------
# top_n_v1 tier (cap < n < 2*cap)
# ---------------------------------------------------------------------------


class TestTopNV1:
    def test_top_n_selects_highest_wmc(self):
        # 6 classes, cap=4 → top_n_v1 (4 < 6 < 8)
        nodes = [
            _make_class_node(f"com.example.orders.C{i}", wmc=i, cbo=0)
            for i in range(6)  # wmc 0..5
        ]
        graph = _make_graph(nodes)
        selector = ClassSelector(cap=4)
        results = selector.select(graph)

        result = results[0]
        assert result.strategy == "top_n_v1"
        assert len(result.selected) == 4

        assert set(result.selected) == {
            "com.example.orders.C5",
            "com.example.orders.C4",
            "com.example.orders.C3",
            "com.example.orders.C2",
        }
        assert set(result.excluded) == {
            "com.example.orders.C0",
            "com.example.orders.C1",
        }

    def test_top_n_nulls_wmc_go_last(self):
        nodes = [
            _make_class_node("com.example.orders.C1", wmc=10, cbo=0),
            _make_class_node("com.example.orders.C2", wmc=8, cbo=0),
            _make_class_node("com.example.orders.C3", wmc=None, cbo=0),
            _make_class_node("com.example.orders.C4", wmc=None, cbo=0),
        ]
        graph = _make_graph(nodes)
        selector = ClassSelector(cap=3)
        results = selector.select(graph)

        result = results[0]
        assert result.strategy == "top_n_v1"
        assert len(result.selected) == 3
        assert "com.example.orders.C1" in result.selected
        assert "com.example.orders.C2" in result.selected
        assert len(result.excluded) == 1
        assert list(result.excluded)[0] in ("com.example.orders.C3", "com.example.orders.C4")


# ---------------------------------------------------------------------------
# stratified_threshold_v1 tier (n ≥ 2*cap)
# ---------------------------------------------------------------------------


class TestStratifiedThresholdV1:
    def test_high_bucket_prioritised(self):
        # 1 high class + many low classes, cap=1 → high class must be selected.
        high = _make_class_node(
            "com.example.orders.HighClass",
            cbo=_HIGH_CBO_THRESHOLD,
            wmc=1,
        )
        lows = [_make_class_node(f"com.example.orders.LowClass{i}", cbo=0, wmc=0) for i in range(3)]
        graph = _make_graph([high, *lows])
        selector = ClassSelector(cap=1)
        results = selector.select(graph)

        result = results[0]
        assert result.strategy == "stratified_threshold_v1"
        assert "com.example.orders.HighClass" in result.selected

    def test_high_count_recorded(self):
        highs = [
            _make_class_node(
                f"com.example.orders.H{i}",
                cbo=_HIGH_CBO_THRESHOLD,
                wmc=_HIGH_WMC_THRESHOLD,
            )
            for i in range(3)
        ]
        lows = [_make_class_node(f"com.example.orders.L{i}", cbo=0, wmc=0) for i in range(5)]
        graph = _make_graph(highs + lows)
        selector = ClassSelector(cap=4)
        results = selector.select(graph)

        result = results[0]
        assert result.strategy == "stratified_threshold_v1"
        assert result.high_count == 3

    def test_metrics_missing_classes_go_to_mid(self):
        # Classes without metrics should appear in mid-bucket, not crash.
        no_metrics = [
            _make_class_node(
                f"com.example.orders.NoMetrics{i}",
                cbo=None,
                wmc=None,
                extraction_mode="signatures_only",
            )
            for i in range(4)
        ]
        graph = _make_graph(no_metrics)
        selector = ClassSelector(cap=2)
        results = selector.select(graph)

        result = results[0]
        assert result.metrics_missing_count == 4
        assert len(result.selected) == 2
        assert len(result.excluded) == 2

    def test_selected_never_exceeds_cap(self):
        nodes = [_make_class_node(f"com.example.orders.C{i}", cbo=i, wmc=i) for i in range(8)]
        graph = _make_graph(nodes)
        selector = ClassSelector(cap=3)
        results = selector.select(graph)

        for result in results:
            assert len(result.selected) <= 3

    def test_small_budget_round_robin_spread(self):
        """D-009-1 Confirmation: cap=3 with all three buckets populated must yield
        exactly one class from each difficulty band (high, mid, low), not three highs.
        This is the DC3-01 regression test — the old sequential fill would have
        returned [H1,H2,H3] with zero mid/low representation.
        """
        # high bucket: CBO ≥ 5 OR WMC ≥ 20
        highs = [
            _make_class_node(f"com.example.orders.H{i}", cbo=_HIGH_CBO_THRESHOLD, wmc=25 - i)
            for i in range(3)
        ]
        # mid bucket: not high, not low
        mids = [
            _make_class_node(f"com.example.orders.M{i}", cbo=2, wmc=10)
            for i in range(3)
        ]
        # low bucket: CBO ≤ 1 AND WMC ≤ 5
        lows = [
            _make_class_node(f"com.example.orders.L{i}", cbo=0, wmc=1)
            for i in range(3)
        ]
        graph = _make_graph(highs + mids + lows)
        # n=9 ≥ 2*cap=6 → stratified_threshold_v1 fires
        selector = ClassSelector(cap=3)
        results = selector.select(graph)

        assert len(results) == 1
        result = results[0]
        assert result.strategy == "stratified_threshold_v1"
        assert len(result.selected) == 3

        selected_set = set(result.selected)
        # Must include at least one from each bucket
        assert any(s.startswith("com.example.orders.H") for s in selected_set), (
            "Round-robin must pick at least one high-complexity class"
        )
        assert any(s.startswith("com.example.orders.M") for s in selected_set), (
            "Round-robin must pick at least one mid-complexity class"
        )
        assert any(s.startswith("com.example.orders.L") for s in selected_set), (
            "Round-robin must pick at least one low-complexity class"
        )

    def test_round_robin_exhausted_buckets_filled_from_remaining(self):
        """When one bucket is exhausted mid-run, subsequent cycles skip it and continue
        pulling from the remaining populated buckets until cap is reached.
        """
        # Only 1 low class — after cycle 1 it is exhausted; cycles 2+ skip low.
        # n=7, cap=3 → 7 ≥ 2*3=6 → stratified_threshold_v1 fires.
        highs = [_make_class_node(f"com.example.orders.H{i}", cbo=_HIGH_CBO_THRESHOLD, wmc=20) for i in range(3)]
        mids = [_make_class_node(f"com.example.orders.M{i}", cbo=2, wmc=10) for i in range(3)]
        lows = [_make_class_node("com.example.orders.L0", cbo=0, wmc=1)]
        graph = _make_graph(highs + mids + lows)
        selector = ClassSelector(cap=3)
        results = selector.select(graph)
        result = results[0]
        assert result.strategy == "stratified_threshold_v1"
        assert len(result.selected) == 3
        # Cycle 1 picks one from each: H0, M0, L0. Cap reached.
        selected = set(result.selected)
        assert "com.example.orders.L0" in selected  # the only low must be picked in cycle 1
        assert any(s.startswith("com.example.orders.H") for s in selected)
        assert any(s.startswith("com.example.orders.M") for s in selected)


# ---------------------------------------------------------------------------
# SelectionResult immutability
# ---------------------------------------------------------------------------


class TestSelectionResult:
    def test_frozen(self):
        result = SelectionResult(
            selected=("com.example.A",),
            excluded=(),
            strategy="take_all",
            group_name="orders",
            cap=50,
            total_in_group=1,
            metrics_missing_count=0,
            high_count=0,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.strategy = "mutated"  # type: ignore[misc]

    def test_adr010_extension_fields_default_empty(self):
        result = SelectionResult(
            selected=(),
            excluded=(),
            strategy="take_all",
            group_name="misc",
            cap=50,
            total_in_group=0,
            metrics_missing_count=0,
            high_count=0,
        )
        assert result.refused == ()
        assert result.stub_todos == ()
        assert result.feature_policies_active == ()
