"""Unit tests for graph-quality check implementations (ADR-017 Fork 3).

Tests structural_completeness, relationship_correctness, internal_consistency,
semantic_accuracy, and schema_validity using lightweight in-memory graphs.
reproducibility and golden_graph_agreement are filesystem/subprocess-heavy
and are tested via skip-path unit tests only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeograph.graph.models.graph_schema import (
    CallsResolvedEdge,
    ClassNode,
    CodeographKnowledgeGraph,
    DependsOnEdge,
    Edge,
    ExtractionMode,
    MethodNode,
    Node,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _class_node(
    fqcn: str = "com.example.Foo",
    extraction_mode: str = "ast",
) -> Node:
    return Node(
        root=ClassNode(
            id=fqcn,
            name=fqcn.rsplit(".", 1)[-1],
            kind="class",
            modifiers=["public"],
            source_file=f"src/{fqcn.replace('.', '/')}.java",
            line_range=[1, 10],
            extraction_mode=ExtractionMode(extraction_mode),
            annotations=[],
        )
    )


def _method_node(fqcn: str = "com.example.Foo#bar()") -> Node:
    return Node(
        root=MethodNode(
            id=fqcn,
            name=fqcn.split("#")[1].split("(")[0],
            kind="method",
            modifiers=["public"],
            line_range=[2, 5],
            parameters=[],
            return_type="void",
            is_constructor=False,
        )
    )


def _depends_on_edge(source: str, target: str) -> Edge:
    return Edge(root=DependsOnEdge(source=source, target=target, kind="depends_on"))


def _calls_resolved_edge(source: str, target: str) -> Edge:
    return Edge(root=CallsResolvedEdge(source=source, target=target, kind="calls_resolved", call_count=1))


def _empty_graph() -> CodeographKnowledgeGraph:
    return CodeographKnowledgeGraph(nodes=[], edges=[])


# ---------------------------------------------------------------------------
# structural_completeness
# ---------------------------------------------------------------------------


class TestStructuralCompleteness:
    def test_empty_graph_returns_one(self):
        from codeograph.evals.checks.graph.structural_completeness import check_structural_completeness

        result = check_structural_completeness(_empty_graph())
        assert result.value == 1.0
        assert result.result == "pass"

    def test_all_ast_nodes_returns_one(self):
        from codeograph.evals.checks.graph.structural_completeness import check_structural_completeness

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.A", "ast"), _class_node("com.example.B", "ast")],
            edges=[],
        )
        result = check_structural_completeness(graph)
        assert result.value == 1.0
        assert result.result == "pass"

    def test_regex_node_lowers_value(self):
        from codeograph.evals.checks.graph.structural_completeness import check_structural_completeness

        graph = CodeographKnowledgeGraph(
            nodes=[
                _class_node("com.example.A", "ast"),
                _class_node("com.example.B", "regex_fallback"),
            ],
            edges=[],
        )
        result = check_structural_completeness(graph)
        assert result.value == pytest.approx(0.5)
        assert result.result == "fail"

    def test_details_contain_counts(self):
        from codeograph.evals.checks.graph.structural_completeness import check_structural_completeness

        graph = CodeographKnowledgeGraph(nodes=[_class_node()], edges=[])
        result = check_structural_completeness(graph)
        assert "total_nodes" in result.details
        assert "ast_nodes" in result.details
        assert result.details["total_nodes"] == 1


# ---------------------------------------------------------------------------
# relationship_correctness
# ---------------------------------------------------------------------------


class TestRelationshipCorrectness:
    def test_empty_graph_returns_one(self):
        from codeograph.evals.checks.graph.relationship_correctness import check_relationship_correctness

        result = check_relationship_correctness(_empty_graph())
        assert result.value == 1.0
        assert result.result == "pass"

    def test_resolved_edge_returns_one(self):
        from codeograph.evals.checks.graph.relationship_correctness import check_relationship_correctness

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.A"), _class_node("com.example.B")],
            edges=[_depends_on_edge("com.example.A", "com.example.B")],
        )
        result = check_relationship_correctness(graph)
        assert result.value == 1.0

    def test_dangling_calls_resolved_edge_lowers_value(self):
        # A calls_resolved edge pointing to a missing target lowers the ratio.
        # (depends_on edges with missing targets are not scored — only calls_resolved.)
        from codeograph.evals.checks.graph.relationship_correctness import check_relationship_correctness

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.A")],
            edges=[_calls_resolved_edge("com.example.A", "com.example.Missing")],
        )
        result = check_relationship_correctness(graph)
        assert result.value < 1.0
        assert result.result == "fail"

    def test_depends_on_edge_with_missing_target_does_not_lower_value(self):
        # depends_on edges are excluded from the call-resolution ratio.
        from codeograph.evals.checks.graph.relationship_correctness import check_relationship_correctness

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.A")],
            edges=[_depends_on_edge("com.example.A", "com.example.Missing")],
        )
        result = check_relationship_correctness(graph)
        assert result.value == 1.0  # no calls_resolved edges → default 1.0
        assert result.result == "pass"

    def test_details_contain_edge_counts(self):
        from codeograph.evals.checks.graph.relationship_correctness import check_relationship_correctness

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.A"), _class_node("com.example.B")],
            edges=[_calls_resolved_edge("com.example.A", "com.example.B")],
        )
        result = check_relationship_correctness(graph)
        assert "total_edges" in result.details
        assert "resolved_call_edges" in result.details
        assert "broken_resolved_call_edges" in result.details


# ---------------------------------------------------------------------------
# internal_consistency
# ---------------------------------------------------------------------------


class TestInternalConsistency:
    def test_empty_graph_zero_violations(self):
        from codeograph.evals.checks.graph.internal_consistency import check_internal_consistency

        result = check_internal_consistency(_empty_graph())
        assert result.value == 0
        assert result.result == "pass"

    def test_valid_graph_zero_violations(self):
        from codeograph.evals.checks.graph.internal_consistency import check_internal_consistency

        graph = CodeographKnowledgeGraph(
            nodes=[_class_node("com.example.Foo"), _method_node("com.example.Foo#bar()")],
            edges=[],
        )
        result = check_internal_consistency(graph)
        assert result.value == 0

    def test_method_with_missing_parent_class_is_violation(self):
        from codeograph.evals.checks.graph.internal_consistency import check_internal_consistency

        # Method whose parent FQCN does not exist in the graph
        graph = CodeographKnowledgeGraph(
            nodes=[_method_node("com.example.Orphan#doSomething()")],
            edges=[],
        )
        result = check_internal_consistency(graph)
        assert result.value >= 1

    def test_violations_listed_in_details(self):
        from codeograph.evals.checks.graph.internal_consistency import check_internal_consistency

        graph = CodeographKnowledgeGraph(
            nodes=[_method_node("com.example.Ghost#run()")],
            edges=[],
        )
        result = check_internal_consistency(graph)
        assert "violations" in result.details
        assert len(result.details["violations"]) >= 1


# ---------------------------------------------------------------------------
# semantic_accuracy — always deferred skip
# ---------------------------------------------------------------------------


def test_semantic_accuracy_always_skips():
    from codeograph.evals.checks.graph.semantic_accuracy import check_semantic_accuracy

    result = check_semantic_accuracy(_empty_graph())
    assert result.result == "skip"
    assert result.details.get("skip_reason") == "deferred_v1.1"
    assert result.details.get("owner_adr") == "ADR-020"


# ---------------------------------------------------------------------------
# schema_validity — uses real schema file
# ---------------------------------------------------------------------------


def test_schema_validity_passes_for_valid_graph():
    from codeograph.evals.checks.graph.schema_validity import check_schema_validity

    result = check_schema_validity(_empty_graph())
    assert result.result == "pass"
    assert result.value is True


# ---------------------------------------------------------------------------
# reproducibility — skip path (no source_path in manifest)
# ---------------------------------------------------------------------------


def test_reproducibility_skips_when_source_path_empty(tmp_path: Path):
    from codeograph.evals.checks.graph.reproducibility import check_reproducibility

    manifest = {
        "schema_version": "1.6.0",
        "codeograph_version": "0.1.0",
        "source_path": "",
        "corpus_id": "test",
        "artefacts": {
            "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
            "llm_annotations": {"path": "llm-annotations.json", "schema_version": "1.0.0", "sha256": None},
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = check_reproducibility(tmp_path)
    assert result.result == "skip"
    assert result.details["skip_reason"] == "source_path_unavailable"


# ---------------------------------------------------------------------------
# golden_graph_agreement — skip path (no golden committed)
# ---------------------------------------------------------------------------


def test_golden_graph_agreement_skips_when_no_golden(tmp_path: Path):
    from codeograph.evals.checks.graph.golden_graph_agreement import check_golden_graph_agreement

    # Check now accepts corpus_id and current_sha256 directly (no manifest read).
    result = check_golden_graph_agreement(
        corpus_id="corpus-that-has-no-golden-xyz",
        current_sha256="a" * 64,
    )
    assert result.result == "skip"
    assert result.details["skip_reason"] == "no_golden_committed"
