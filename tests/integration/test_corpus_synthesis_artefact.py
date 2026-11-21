"""The graph is a function of the corpus alone; Pass 2's synthesis lives in its own indexed file."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import jsonschema
import pytest
from click.testing import CliRunner

from codeograph.cli.main import cli
from tests.integration.test_cli_cost_safety import DynamicMockLlmProvider

# Pass 0 parses Java via the JVM sidecar, so these belong in the Java-enabled Integration job.
pytestmark = pytest.mark.slow

CORPUS = "tests/fixtures/corpora/minimal_rest"
SYNTHESIS_SCHEMA = Path("codeograph/schema/corpus-synthesis.schema.json")


def _run(tmp_path: Path, *extra: str) -> Path:
    out = tmp_path / "out"
    with patch("codeograph.llm.resolver.LlmProviderResolver.resolve", return_value=DynamicMockLlmProvider()):
        result = CliRunner().invoke(
            cli,
            ["run", CORPUS, "--out", str(out), "--yes", *extra],
            env={"CODEOGRAPH_CACHE_DIR": str(tmp_path / "cache")},
        )
    assert result.exit_code == 0, result.output
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_llm_run_graph_is_byte_identical_to_ast_only_graph(tmp_path):
    ast_only_out = _run(tmp_path / "ast_only", "--ast-only")
    full_out = _run(tmp_path / "full")

    full_graph = (full_out / "graph.json").read_bytes()
    assert full_graph == (ast_only_out / "graph.json").read_bytes()
    assert "projectOverview" not in full_graph.decode("utf-8")


def test_manifest_hashes_describe_the_files_on_disk(tmp_path):
    out = _run(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    artefacts = manifest["artefacts"]

    assert artefacts["graph"]["sha256"] == _sha256(out / "graph.json")

    pointer = artefacts["corpus_synthesis"]
    assert pointer["path"] == "corpus-synthesis.json"
    assert pointer["schema_version"] == "1.0.0"
    assert pointer["sha256"] == _sha256(out / "corpus-synthesis.json")


def test_corpus_synthesis_file_validates_against_its_schema(tmp_path):
    out = _run(tmp_path)
    document = json.loads((out / "corpus-synthesis.json").read_text(encoding="utf-8"))
    schema = json.loads(SYNTHESIS_SCHEMA.read_text(encoding="utf-8"))

    jsonschema.validate(document, schema)
    assert document["schema_version"] == "1.0.0"


def test_ast_only_run_writes_no_synthesis_file_and_no_pointer(tmp_path):
    out = _run(tmp_path, "--ast-only")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert not (out / "corpus-synthesis.json").exists()
    assert "corpus_synthesis" not in manifest["artefacts"]
