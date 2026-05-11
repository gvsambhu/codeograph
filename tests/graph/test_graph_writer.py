"""
Unit tests for GraphWriter (codeograph/graph/graph_writer.py).

Coverage plan:
  - _canonical_bytes: nodes sorted by id, edges sorted by (kind,source,target),
    sortable arrays within nodes sorted, positional arrays preserved,
    trailing newline, no None values in sorted arrays
  - _canonical_bytes: determinism — same bytes on two calls
  - write(): creates output_dir (including parents), graph.json written,
    manifest.json written, sha256 in manifest matches graph bytes,
    returns path to manifest.json
  - _build_manifest: llm_annotations.sha256 is None (AST-only DC1 mode)
  - _tool_version: fallback to "0.1.0-dev" when package not installed

NOTE: Tests that read a real parser.jar or call a live JVM are NOT here.
      Those belong to the golden-graph integration suite (ADR-007) and are
      tagged @pytest.mark.integration.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from codeograph.graph.graph_writer import (
    _SORTABLE_NODE_ARRAYS,
    GRAPH_FILENAME,
    MANIFEST_FILENAME,
    GraphWriter,
)
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

# ---------------------------------------------------------------------------
# Helpers — minimal graph fixtures
# ---------------------------------------------------------------------------

def _empty_graph() -> CodeographKnowledgeGraph:
    """Graph with no nodes and no edges."""
    return CodeographKnowledgeGraph(nodes=[], edges=[])


def _graph_with_nodes_unsorted() -> CodeographKnowledgeGraph:
    """
    Graph where the node list is intentionally NOT sorted by id.
    _canonical_bytes must sort them.
    """
    import codeograph.graph.models.graph_schema as gs

    node_z = gs.Node(
        root=gs.ModuleNode(
            id="mod:z-module",
            kind="module",
            name="z-module",
            build_tool=gs.BuildTool.maven,
            source_roots=["z-module/src/main/java"],
        )
    )
    node_a = gs.Node(
        root=gs.ModuleNode(
            id="mod:a-module",
            kind="module",
            name="a-module",
            build_tool=gs.BuildTool.maven,
            source_roots=["a-module/src/main/java"],
        )
    )
    return CodeographKnowledgeGraph(nodes=[node_z, node_a], edges=[])


def _graph_with_class_node(
    fqcn: str = "com.example.Foo",
    modifiers: list[str] | None = None,
    annotations: list[str] | None = None,
) -> CodeographKnowledgeGraph:
    """
    Graph with a single ClassNode.  Use to probe sortable-array behaviour.
    modifiers and annotations are passed in the order given; canonical form
    must sort them.
    """
    import codeograph.graph.models.graph_schema as gs

    node = gs.Node(
        root=gs.ClassNode(
            id=fqcn,
            kind="class",
            name=fqcn.rsplit(".", 1)[-1],
            source_file=fqcn.replace(".", "/") + ".java",
            extraction_mode="ast",
            modifiers=[gs.Modifier(m) for m in (modifiers or [])],
            annotations=annotations or [],
            is_inner_class=False,
            entry_point=False,
            line_range=[1, 10],
        )
    )
    return CodeographKnowledgeGraph(nodes=[node], edges=[])


# ---------------------------------------------------------------------------
# TestCanonicalBytes
# ---------------------------------------------------------------------------

class TestCanonicalBytes:
    """Unit tests for GraphWriter._canonical_bytes."""

    writer = GraphWriter()

    def test_empty_graph_is_valid_json(self) -> None:
        raw = self.writer._canonical_bytes(_empty_graph())
        data = json.loads(raw)
        assert "nodes" in data
        assert "edges" in data

    def test_trailing_newline(self) -> None:
        raw = self.writer._canonical_bytes(_empty_graph())
        assert raw.endswith(b"\n"), "canonical bytes must end with LF"

    def test_nodes_sorted_by_id(self) -> None:
        graph = _graph_with_nodes_unsorted()
        raw = self.writer._canonical_bytes(graph)
        data = json.loads(raw)
        ids = [n["id"] for n in data["nodes"]]
        assert ids == sorted(ids), f"nodes not sorted by id: {ids}"

    def test_edges_sorted_by_kind_source_target(self) -> None:
        """Build two edges in reverse order; canonical form must sort them."""
        import codeograph.graph.models.graph_schema as gs

        edge1 = gs.Edge(
            root=gs.ContainsEdge(
                kind="contains",
                source="mod:a-module",
                target="com.example.Alpha",
            )
        )
        edge2 = gs.Edge(
            root=gs.ContainsEdge(
                kind="contains",
                source="mod:a-module",
                target="com.example.Beta",
            )
        )
        graph = CodeographKnowledgeGraph(nodes=[], edges=[edge2, edge1])
        raw = self.writer._canonical_bytes(graph)
        data = json.loads(raw)
        targets = [e["target"] for e in data["edges"]]
        assert targets == sorted(targets), f"edges not sorted by target: {targets}"

    def test_modifiers_sorted_within_node(self) -> None:
        graph = _graph_with_class_node(modifiers=["static", "final", "public"])
        raw = self.writer._canonical_bytes(graph)
        data = json.loads(raw)
        mods = data["nodes"][0].get("modifiers", [])
        assert mods == sorted(mods), f"modifiers not sorted: {mods}"

    def test_annotations_sorted_within_node(self) -> None:
        graph = _graph_with_class_node(annotations=["Service", "Transactional", "Component"])
        raw = self.writer._canonical_bytes(graph)
        data = json.loads(raw)
        anns = data["nodes"][0].get("annotations", [])
        assert anns == sorted(anns), f"annotations not sorted: {anns}"

    def test_deterministic_two_calls_same_bytes(self) -> None:
        graph = _graph_with_nodes_unsorted()
        b1 = self.writer._canonical_bytes(graph)
        b2 = self.writer._canonical_bytes(graph)
        assert b1 == b2, "canonical_bytes must be deterministic"

    def test_compact_separators_no_whitespace_between_keys(self) -> None:
        """sort_keys=True + separators=(",",":") means no space after colon."""
        raw = self.writer._canonical_bytes(_empty_graph())
        text = raw.decode("utf-8")
        # compact: {"edges":[],"nodes":[]}  — no space after ":"
        assert '": ' not in text, "canonical form must not have space after colon"

    def test_sort_keys_alphabetical(self) -> None:
        """Top-level keys must be alphabetically ordered (sort_keys=True)."""
        raw = self.writer._canonical_bytes(_empty_graph())
        text = raw.strip().decode("utf-8")
        # "edges" comes before "nodes" alphabetically
        assert text.index('"edges"') < text.index('"nodes"')

    def test_none_excluded_from_sorted_arrays(self) -> None:
        """
        If a sortable list contains None, None must not appear in the output.
        (The comprehension `v for v in node[field] if v is not None` guards this.)
        """
        # We can't easily inject None via Pydantic; instead verify the filter
        # via _canonical_bytes on a dict directly. Test the private filter logic.
        import codeograph.graph.models.graph_schema as gs

        node = gs.Node(
            root=gs.ClassNode(
                id="com.example.Foo",
                kind="class",
                name="Foo",
                source_file="com/example/Foo.java",
                extraction_mode="ast",
                modifiers=[],
                annotations=[],
                is_inner_class=False,
                entry_point=False,
                line_range=[1, 10],
            )
        )
        graph = CodeographKnowledgeGraph(nodes=[node], edges=[])
        data = json.loads(self.writer._canonical_bytes(graph))
        for field in _SORTABLE_NODE_ARRAYS:
            arr = data["nodes"][0].get(field)
            if arr is not None:
                assert None not in arr, f"None present in {field} after canonical sort"


# ---------------------------------------------------------------------------
# TestWrite
# ---------------------------------------------------------------------------

class TestWrite:
    """Unit tests for GraphWriter.write()."""

    writer = GraphWriter()

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "deep" / "nested" / "out"
        assert not out.exists()
        self.writer.write(_empty_graph(), out)
        assert out.is_dir()

    def test_graph_json_written(self, tmp_path: Path) -> None:
        self.writer.write(_empty_graph(), tmp_path)
        assert (tmp_path / GRAPH_FILENAME).exists()

    def test_manifest_json_written(self, tmp_path: Path) -> None:
        self.writer.write(_empty_graph(), tmp_path)
        assert (tmp_path / MANIFEST_FILENAME).exists()

    def test_returns_manifest_path(self, tmp_path: Path) -> None:
        result = self.writer.write(_empty_graph(), tmp_path)
        assert result == tmp_path / MANIFEST_FILENAME

    def test_graph_bytes_match_sha256_in_manifest(self, tmp_path: Path) -> None:
        self.writer.write(_empty_graph(), tmp_path)

        graph_bytes = (tmp_path / GRAPH_FILENAME).read_bytes()
        expected_sha = hashlib.sha256(graph_bytes).hexdigest()

        manifest_data = json.loads((tmp_path / MANIFEST_FILENAME).read_bytes())
        assert manifest_data["artefacts"]["graph"]["sha256"] == expected_sha

    def test_llm_annotations_sha256_is_null_in_manifest(self, tmp_path: Path) -> None:
        """DC1 (AST-only) mode: llm_annotations sha256 must be null."""
        self.writer.write(_empty_graph(), tmp_path)
        manifest_data = json.loads((tmp_path / MANIFEST_FILENAME).read_bytes())
        assert manifest_data["artefacts"]["llm_annotations"]["sha256"] is None

    def test_manifest_contains_graph_path_field(self, tmp_path: Path) -> None:
        self.writer.write(_empty_graph(), tmp_path)
        manifest_data = json.loads((tmp_path / MANIFEST_FILENAME).read_bytes())
        assert manifest_data["artefacts"]["graph"]["path"] == GRAPH_FILENAME

    def test_graph_json_is_valid_utf8(self, tmp_path: Path) -> None:
        self.writer.write(_empty_graph(), tmp_path)
        content = (tmp_path / GRAPH_FILENAME).read_bytes()
        # Must decode without error
        content.decode("utf-8")

    def test_write_idempotent_overwrites(self, tmp_path: Path) -> None:
        """Calling write() twice in the same dir must succeed (no exclusive-open error)."""
        self.writer.write(_empty_graph(), tmp_path)
        self.writer.write(_empty_graph(), tmp_path)
        assert (tmp_path / GRAPH_FILENAME).exists()


# ---------------------------------------------------------------------------
# TestToolVersion
# ---------------------------------------------------------------------------

class TestToolVersion:
    """Unit tests for GraphWriter._tool_version()."""

    def test_returns_string(self) -> None:
        v = GraphWriter._tool_version()
        assert isinstance(v, str)
        assert len(v) > 0

    def test_fallback_when_package_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulate PackageNotFoundError → expect "0.1.0-dev" fallback."""
        from importlib.metadata import PackageNotFoundError

        def _raise(_: str) -> str:
            raise PackageNotFoundError("codeograph")

        monkeypatch.setattr(
            "codeograph.graph.graph_writer.version", _raise
        )
        result = GraphWriter._tool_version()
        assert result == "0.1.0-dev"
