"""Integration test for the B-amendment Confirmation #10 (no manifest on interrupt).

Scaffolding is AI-generated; the assertion body is learner-write per the
DC5 M12 spec.

Per the ADR-025 terminal-write protocol amendment (the 2026-06-08
``## Amendments`` entry):

> 10. A full run interrupted after the graph pass — before the LLM pass
>     writes ``llm-annotations.json`` — leaves **no** ``manifest.json`` on
>     disk (``graph.json`` may exist; the manifest appears only at the
>     terminal write). Equivalently: at no point during a run does an
>     on-disk manifest violate the §Invariants (integration test).

This is the new Confirmation item that the amendment adds to the 9
already in the original ADR-025 body. It codifies the "terminal-write
only" pattern: if the run doesn't reach the terminal write, no
manifest is left behind.
"""

from __future__ import annotations

# Imports used by the learner-written assertion bodies; suppress
# unused-import warnings until the bodies are filled in.
import json  # noqa: F401
import subprocess  # noqa: F401
import sys  # noqa: F401
from pathlib import Path  # noqa: F401
from unittest.mock import patch  # noqa: F401

import pytest  # noqa: F401

# ---------------------------------------------------------------------------
# TestNoManifestOnInterrupt (Amendment Confirmation #10)
# ---------------------------------------------------------------------------


class TestNoManifestOnInterrupt:
    """A full run interrupted after the graph pass leaves no manifest."""

    def test_no_manifest_when_graph_passes_but_llm_fails(self, tmp_path: Path, monkeypatch) -> None:
        # TODO(learner): arrange a run where the graph pass succeeds
        # (writes graph.json to out_dir) but the LLM pass raises before
        # producing llm-annotations.json. Assert that no manifest.json
        # exists in out_dir at the point of the exception.
        #
        # Implementation hints:
        # 1. Patch ``codeograph.passes.pass1.annotator.NodeAnnotator.annotate``
        #    to raise (simulates a Pass 1 crash).
        # 2. Invoke the orchestrator (you can either call the inner
        #    logic of `cli/main.py:run` directly, or use the CliRunner
        #    with a mocked LLM stack + an ``--ast-only=False`` flag).
        # 3. Catch the exception; assert
        #    ``not (out_dir / "manifest.json").exists()`` and
        #    ``(out_dir / "graph.json").exists()``.
        # 4. The strengthened invariant holds: no on-disk manifest
        #    ever violates the §Invariants because no on-disk
        #    manifest ever exists in the intermediate window.
        ...


# ---------------------------------------------------------------------------
# TestTerminalWritePresenceImpliesValid
# ---------------------------------------------------------------------------


class TestTerminalWritePresenceImpliesValid:
    """If a manifest IS on disk, it satisfies all §Invariants (i.e., the
    assembler only ever produces valid manifests, and only the assembler
    writes the manifest)."""

    def test_manifest_written_by_run_satisfies_all_invariants(self, tmp_path: Path) -> None:
        # TODO(learner): invoke the assembler directly (no subprocess),
        # write the manifest, re-read it via manifest_io.read, and
        # assert the strengthened invariant: ``artefacts.graph`` is
        # always present; every present pointer's sha256 is non-null
        # and 64-hex; if llm_skipped is False, llm_annotations is
        # present; if llm_skipped is True, llm_annotations is absent.
        ...
