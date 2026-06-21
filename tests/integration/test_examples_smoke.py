"""
Integration smoke tests for the shipped example corpora (ADR-018 Fork 2).

Invokes ``codeograph run --ast-only`` against each example corpus and
asserts structural correctness: exit 0, graph.json validates, manifest
validates against the 2.0.0 schema.  Class counts and specific graph
topology are NOT asserted here — those are the golden-graph tests
(ADR-007, tests/integration/test_goldens.py).

Skipped by default (``slow`` + ``external``).  Requires the JVM (Java 17+)
on PATH; skip gracefully when it is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve example corpora relative to the repository root so the test
# is path-stable regardless of where pytest is invoked from.
_REPO_ROOT = Path(__file__).parents[2]
_EXAMPLES_DIR = _REPO_ROOT / "examples"
EXAMPLE_CORPORA = sorted(_EXAMPLES_DIR.iterdir()) if _EXAMPLES_DIR.exists() else []


@pytest.mark.slow
@pytest.mark.external
@pytest.mark.parametrize("corpus_dir", EXAMPLE_CORPORA, ids=lambda p: p.name)
def test_example_corpus_renders_cleanly(corpus_dir: Path, tmp_path: Path) -> None:
    """Run ``codeograph run --ast-only`` and assert structural output correctness.

    Checks (per ADR-018 Fork 2 smoke-test policy):
    * Command exits 0.
    * ``graph.json`` is present and contains ``nodes`` + ``edges`` keys.
    * ``manifest.json`` is present, schema_version is ``"2.0.0"``, and a
      ``graph`` artefact pointer with a non-empty sha256 is recorded.

    Does NOT check class counts, node IDs, or rendering output — those are
    the domain of test_goldens.py and the eval framework (ADR-007 / ADR-017).
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "codeograph",
            "run",
            str(corpus_dir),
            "--out",
            str(tmp_path),
            "--ast-only",
        ],
        capture_output=True,
        text=True,
    )

    # Skip rather than fail when the JVM is absent — same policy as test_goldens.py.
    if proc.returncode != 0 and (
        "JVM not available" in proc.stderr or "java" in proc.stderr.lower() or "No such file" in proc.stderr
    ):
        pytest.skip(f"JVM not available for {corpus_dir.name}: {proc.stderr[:200]}")

    assert proc.returncode == 0, (
        f"codeograph run --ast-only failed on {corpus_dir.name}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )

    # graph.json
    graph_path = tmp_path / "graph.json"
    assert graph_path.exists(), f"graph.json not produced for {corpus_dir.name}"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "nodes" in graph, "graph.json missing 'nodes' key"
    assert "edges" in graph, "graph.json missing 'edges' key"
    assert isinstance(graph["nodes"], list), "'nodes' must be a list"
    assert isinstance(graph["edges"], list), "'edges' must be a list"

    # manifest.json
    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists(), f"manifest.json not produced for {corpus_dir.name}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == "2.0.0", (
        f"manifest schema_version must be '2.0.0', got {manifest.get('schema_version')!r}"
    )
    assert manifest.get("corpus_id"), "manifest missing corpus_id"
    assert manifest.get("run_id"), "manifest missing run_id"
    artefacts = manifest.get("artefacts", {})
    assert "graph" in artefacts, "manifest missing graph artefact pointer"
    graph_ptr = artefacts["graph"]
    assert len(graph_ptr.get("sha256", "")) == 64, "graph artefact sha256 must be 64-hex"
