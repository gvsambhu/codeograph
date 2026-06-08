"""Unit tests for ``ManifestAssembler`` (ADR-025 Confirmations 1, 2).

Scaffolding is AI-generated; the assertion bodies are learner-write per the
DC5 M12 spec. Each test has a ``# TODO(learner):`` marker naming the
ADR-025 Confirmation item it implements.

Per ADR-025 §"Confirmation":
* 1 — A full run produces a manifest with ``schema_version == "2.0.0"``,
      ``llm_skipped == false``, and both ``artefacts.graph`` and
      ``artefacts.llm_annotations`` present with non-null ``sha256``
      matching ``^[0-9a-f]{64}$``.
* 2 — An ``--ast-only`` run produces ``llm_skipped == true``, **no**
      ``llm_annotations`` key under ``artefacts``, and no ``cache_stats``.
"""
from __future__ import annotations

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
from pathlib import Path  # noqa: F401

import pytest  # noqa: F401

from codeograph.manifest import ManifestAssembler  # noqa: F401
from codeograph.manifest.artefact import GraphArtefact

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


# ---------------------------------------------------------------------------
# TestFullRunAssemble (Confirmation #1)
# ---------------------------------------------------------------------------


class TestFullRunAssemble:
    """ADR-025 Confirmation #1: full run shape — ``llm_skipped=False``,
    both graph and llm_annotations pointers present with non-null sha256."""

    def test_schema_version_is_2_0_0(self, tmp_path: Path) -> None:
        # TODO(learner): assemble a full-run manifest and assert
        # m.schema_version == "2.0.0".
        ...

    def test_llm_skipped_is_false(self, tmp_path: Path) -> None:
        # TODO(learner): assert m.llm_skipped is False (full run).
        ...

    def test_both_artefacts_present(self, tmp_path: Path) -> None:
        # TODO(learner): assert "graph" in m.artefacts and
        # "llm_annotations" in m.artefacts.
        ...

    def test_artefact_shas_are_64_hex(self, tmp_path: Path) -> None:
        # TODO(learner): for each pointer in m.artefacts, assert
        # re.fullmatch(r"^[0-9a-f]{64}$", ptr.sha256) is not None.
        ...


# ---------------------------------------------------------------------------
# TestAstOnlyAssemble (Confirmation #2)
# ---------------------------------------------------------------------------


class TestAstOnlyAssemble:
    """ADR-025 Confirmation #2: ``--ast-only`` shape — ``llm_skipped=True``,
    no ``llm_annotations`` key, no ``cache_stats``."""

    def test_llm_skipped_is_true(self, tmp_path: Path) -> None:
        # TODO(learner): assemble an ast-only manifest and assert
        # m.llm_skipped is True.
        ...

    def test_no_llm_annotations_key(self, tmp_path: Path) -> None:
        # TODO(learner): assert "llm_annotations" NOT in m.artefacts.
        # (The invariant says: present iff llm_skipped is false.)
        ...

    def test_no_cache_stats(self, tmp_path: Path) -> None:
        # TODO(learner): assert m.cache_stats is None.
        ...


# ---------------------------------------------------------------------------
# TestCrossFieldInvariants
# ---------------------------------------------------------------------------


class TestCrossFieldInvariants:
    """The assembler's cross-field preconditions (ValueError on violation)."""

    def test_ast_only_with_llm_annotations_artefact_raises(self, tmp_path: Path) -> None:
        # TODO(learner): assemble with llm_skipped=True and an
        # llm_annotations_artefact provided. Assert ValueError is raised
        # with a message mentioning "llm_skipped=True".
        ...

    def test_full_run_without_llm_annotations_artefact_raises(self, tmp_path: Path) -> None:
        # TODO(learner): assemble with llm_skipped=False and no
        # llm_annotations_artefact. Assert ValueError is raised with
        # a message mentioning "llm_annotations_artefact is None".
        ...


# ---------------------------------------------------------------------------
# TestManifestAssemblerStateless
# ---------------------------------------------------------------------------


class TestManifestAssemblerStateless:
    """The assembler is a reusable actor; same inputs → same output."""

    def test_same_inputs_produce_equal_manifests(self, tmp_path: Path) -> None:
        # TODO(learner): call assemble() twice with the same kwargs; assert
        # the two Manifests are equal (or model_dump_json() equal).
        ...


# ---------------------------------------------------------------------------
# TestWriteTo
# ---------------------------------------------------------------------------


class TestWriteTo:
    """``write_to(manifest, out_dir)`` writes the manifest via ``manifest_io``."""

    def test_write_to_creates_manifest_json(self, tmp_path: Path) -> None:
        # TODO(learner): assemble a manifest and call write_to(tmp_path);
        # assert (tmp_path / "manifest.json").exists().
        ...

    def test_write_to_is_round_trip(self, tmp_path: Path) -> None:
        # TODO(learner): assemble, write, re-read via manifest_io.read;
        # assert the re-read Manifest equals the original.
        ...
