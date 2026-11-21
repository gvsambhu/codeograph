"""Unit tests for ``ManifestAssembler`` (ADR-025 Confirmations 1, 2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from codeograph.manifest import ManifestAssembler
from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.io import read
from codeograph.manifest.models import Manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_artefact(tmp_path: Path) -> GraphArtefact:
    """A conformant ``GraphArtefact`` whose ``path`` lives in ``tmp_path``."""
    graph_path = tmp_path / "graph.json"
    graph_path.write_bytes(b'{"nodes":[],"edges":[]}')
    return GraphArtefact(
        path=graph_path,
        schema_version="1.0.0",
        sha256="a" * 64,
    )


def _llm_annotations_artefact(tmp_path: Path) -> GraphArtefact:
    """A conformant ``GraphArtefact`` for the LLM-annotations file."""
    ann_path = tmp_path / "llm-annotations.json"
    ann_path.write_bytes(b"{}")
    return GraphArtefact(
        path=ann_path,
        schema_version="1.0.0",
        sha256="b" * 64,
    )


def _corpus_synthesis_artefact(tmp_path: Path) -> GraphArtefact:
    """A conformant ``GraphArtefact`` for the corpus-synthesis file."""
    synthesis_path = tmp_path / "corpus-synthesis.json"
    synthesis_path.write_bytes(b"{}")
    return GraphArtefact(
        path=synthesis_path,
        schema_version="1.0.0",
        sha256="c" * 64,
    )


def _assemble_full(tmp_path: Path, *, with_synthesis: bool = False) -> Manifest:
    """Helper to assemble a full-run manifest."""
    assembler = ManifestAssembler()
    return assembler.assemble(
        run_id="2026-06-11T10-00-00Z-a1b2c3",
        codeograph_version="0.1.0",
        source_path=str(tmp_path / "source"),
        corpus_id="test-corpus",
        llm_skipped=False,
        graph_artefact=_graph_artefact(tmp_path),
        llm_annotations_artefact=_llm_annotations_artefact(tmp_path),
        corpus_synthesis_artefact=_corpus_synthesis_artefact(tmp_path) if with_synthesis else None,
    )


def _assemble_ast_only(tmp_path: Path) -> Manifest:
    """Helper to assemble an AST-only manifest."""
    assembler = ManifestAssembler()
    return assembler.assemble(
        run_id="2026-06-11T10-00-00Z-a1b2c3",
        codeograph_version="0.1.0",
        source_path=str(tmp_path / "source"),
        corpus_id="test-corpus",
        llm_skipped=True,
        graph_artefact=_graph_artefact(tmp_path),
    )


# ---------------------------------------------------------------------------
# TestFullRunAssemble (Confirmation #1)
# ---------------------------------------------------------------------------


class TestFullRunAssemble:
    """ADR-025 Confirmation #1: full run shape — ``llm_skipped=False``,
    both graph and llm_annotations pointers present with non-null sha256."""

    def test_schema_version_is_2_0_0(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        assert m.schema_version == "2.0.0"

    def test_llm_skipped_is_false(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        assert m.llm_skipped is False

    def test_both_artefacts_present(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        assert "graph" in m.artefacts
        assert "llm_annotations" in m.artefacts

    def test_artefact_shas_are_64_hex(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        for ptr in m.artefacts.values():
            assert re.fullmatch(r"^[0-9a-f]{64}$", ptr.sha256) is not None


class TestCorpusSynthesisPointer:
    """The corpus-synthesis pointer: indexed on a full run, never on an ``--ast-only`` run,
    and not required on a full run (a failed synthesis must stay representable as absent)."""

    def test_full_run_with_synthesis_indexes_it(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path, with_synthesis=True)
        pointer = m.artefacts["corpus_synthesis"]
        assert pointer.path == "corpus-synthesis.json"
        assert pointer.schema_version == "1.0.0"
        assert pointer.sha256 == "c" * 64

    def test_full_run_without_synthesis_has_no_pointer(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path, with_synthesis=False)
        assert "corpus_synthesis" not in m.artefacts
        assert set(m.artefacts) == {"graph", "llm_annotations"}

    def test_ast_only_with_synthesis_artefact_raises(self, tmp_path: Path) -> None:
        assembler = ManifestAssembler()
        with pytest.raises(ValueError) as excinfo:
            assembler.assemble(
                run_id="2026-06-11T10-00-00Z-a1b2c3",
                codeograph_version="0.1.0",
                source_path=str(tmp_path / "source"),
                corpus_id="test-corpus",
                llm_skipped=True,
                graph_artefact=_graph_artefact(tmp_path),
                corpus_synthesis_artefact=_corpus_synthesis_artefact(tmp_path),
            )
        assert "llm_skipped=True but corpus_synthesis_artefact is set" in str(excinfo.value)

    def test_ast_only_has_no_synthesis_pointer(self, tmp_path: Path) -> None:
        m = _assemble_ast_only(tmp_path)
        assert "corpus_synthesis" not in m.artefacts


# ---------------------------------------------------------------------------
# TestAstOnlyAssemble (Confirmation #2)
# ---------------------------------------------------------------------------


class TestAstOnlyAssemble:
    """ADR-025 Confirmation #2: ``--ast-only`` shape — ``llm_skipped=True``,
    no ``llm_annotations`` key, no ``cache_stats``."""

    def test_llm_skipped_is_true(self, tmp_path: Path) -> None:
        m = _assemble_ast_only(tmp_path)
        assert m.llm_skipped is True

    def test_no_llm_annotations_key(self, tmp_path: Path) -> None:
        m = _assemble_ast_only(tmp_path)
        assert "llm_annotations" not in m.artefacts

    def test_no_cache_stats(self, tmp_path: Path) -> None:
        m = _assemble_ast_only(tmp_path)
        assert m.cache_stats is None


# ---------------------------------------------------------------------------
# TestCrossFieldInvariants
# ---------------------------------------------------------------------------


class TestCrossFieldInvariants:
    """The assembler's cross-field preconditions (ValueError on violation)."""

    def test_ast_only_with_llm_annotations_artefact_raises(self, tmp_path: Path) -> None:
        assembler = ManifestAssembler()
        with pytest.raises(ValueError) as excinfo:
            assembler.assemble(
                run_id="2026-06-11T10-00-00Z-a1b2c3",
                codeograph_version="0.1.0",
                source_path=str(tmp_path / "source"),
                corpus_id="test-corpus",
                llm_skipped=True,
                graph_artefact=_graph_artefact(tmp_path),
                llm_annotations_artefact=_llm_annotations_artefact(tmp_path),
            )
        assert "llm_skipped=True but llm_annotations_artefact is set" in str(excinfo.value)

    def test_full_run_without_llm_annotations_artefact_raises(self, tmp_path: Path) -> None:
        assembler = ManifestAssembler()
        with pytest.raises(ValueError) as excinfo:
            assembler.assemble(
                run_id="2026-06-11T10-00-00Z-a1b2c3",
                codeograph_version="0.1.0",
                source_path=str(tmp_path / "source"),
                corpus_id="test-corpus",
                llm_skipped=False,
                graph_artefact=_graph_artefact(tmp_path),
                llm_annotations_artefact=None,
            )
        assert "llm_skipped=False but llm_annotations_artefact is None" in str(excinfo.value)


# ---------------------------------------------------------------------------
# TestManifestAssemblerStateless
# ---------------------------------------------------------------------------


class TestManifestAssemblerStateless:
    """The assembler is a reusable actor; same inputs → same output."""

    def test_same_inputs_produce_equal_manifests(self, tmp_path: Path) -> None:
        m1 = _assemble_full(tmp_path)
        m2 = _assemble_full(tmp_path)
        assert m1 == m2
        assert m1.model_dump_json() == m2.model_dump_json()


# ---------------------------------------------------------------------------
# TestWriteTo
# ---------------------------------------------------------------------------


class TestWriteTo:
    """``write_to(manifest, out_dir)`` writes the manifest via ``manifest_io``."""

    def test_write_to_creates_manifest_json(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        out_dir = tmp_path / "out"
        assembler = ManifestAssembler()
        manifest_path = assembler.write_to(m, out_dir)
        assert manifest_path.exists()
        assert manifest_path.name == "manifest.json"

    def test_write_to_is_round_trip(self, tmp_path: Path) -> None:
        m = _assemble_full(tmp_path)
        out_dir = tmp_path / "out"
        assembler = ManifestAssembler()
        manifest_path = assembler.write_to(m, out_dir)
        reread = read(manifest_path)
        assert reread == m
