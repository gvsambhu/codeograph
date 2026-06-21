"""Unit tests for the ``codeograph run --eval`` wiring (DC4-A fix).

Verifies that:
  1. ``evaluate_corpus`` is called with in-memory context params so no
     manifest is needed on disk before eval runs (the DC4-A bug).
  2. The scorecards returned by eval reach the single terminal manifest
     write — no second manifest write, no missing scorecards pointer.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from codeograph.manifest.artefact import GraphArtefact
from codeograph.manifest.models import ScorecardPointer

# All infrastructure classes are lazily imported inside ``run()``, so patches
# must target their source modules, not codeograph.cli.main.
_LAZY_PATCH_TARGETS = [
    "codeograph.input.input_acquirer.InputAcquirer",  # [0] acq_cls
    "codeograph.analyzer.corpus_analyzer.CorpusAnalyzer",  # [1] analyzer_cls
    "codeograph.parser.java_file_parser.JavaFileParser",
    "codeograph.parser.file_parser_dispatcher.FileParserDispatcher",
    "codeograph.graph.graph_builder.GraphBuilder",
    "codeograph.graph.graph_assembler.GraphAssembler",
    "codeograph.graph.graph_writer.GraphWriter",
    "codeograph.manifest.run_id.generate_run_id",  # [7] gen_run_id
]

_FIXED_RUN_ID = "2026-06-21T00-00-00Z-aabbcc"


def _fake_artefact(out_dir: Path) -> GraphArtefact:
    sha = hashlib.sha256(b"{}").hexdigest()
    return GraphArtefact(path=out_dir / "graph.json", schema_version="1.0.0", sha256=sha)


def _fake_scorecards() -> dict[str, ScorecardPointer]:
    return {
        "graph": ScorecardPointer(
            path="evals/graph-scorecard.json",
            sha256="b" * 64,
            overall="pass",
        )
    }


def _invoke_run(tmp_path: Path, *, with_eval: bool, scorecards=None):
    """Invoke ``codeograph run --ast-only [--eval]`` with infrastructure mocked.

    Returns ``(CliResult, mock_evaluate_corpus, artefact)``.
    """
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    artefact = _fake_artefact(out)

    from codeograph.cli.main import cli

    with ExitStack() as stack:
        lazy_mocks = [stack.enter_context(patch(t)) for t in _LAZY_PATCH_TARGETS]
        mock_eval = stack.enter_context(
            patch(
                "codeograph.evals.corpus_evaluator.evaluate_corpus",
                return_value=scorecards or {},
            )
        )
        stack.enter_context(patch("codeograph.cli.main._load_settings", return_value=MagicMock()))

        acq_cls, analyzer_cls = lazy_mocks[0], lazy_mocks[1]
        lazy_mocks[7].return_value = _FIXED_RUN_ID  # generate_run_id

        mock_corpus = MagicMock()
        mock_corpus.modules = []
        mock_corpus.corpus_root.resolve.return_value = src
        acq_cls.return_value.acquire.return_value = mock_corpus
        analyzer_cls.return_value.analyze.return_value = artefact

        args = ["run", str(src), "--out", str(out), "--ast-only"]
        if with_eval:
            args.append("--eval")

        result = CliRunner().invoke(cli, args)

    return result, mock_eval, artefact, out


def test_run_eval_exits_zero(tmp_path: Path):
    result, _, _, _ = _invoke_run(tmp_path, with_eval=True, scorecards=_fake_scorecards())
    assert result.exit_code == 0, result.output


def test_run_eval_calls_evaluate_corpus_with_graph_sha256(tmp_path: Path):
    """evaluate_corpus must receive graph_sha256 in-memory (DC4-A: no manifest on disk yet)."""
    _, mock_eval, artefact, _ = _invoke_run(tmp_path, with_eval=True, scorecards=_fake_scorecards())

    mock_eval.assert_called_once()
    assert mock_eval.call_args.kwargs.get("graph_sha256") == artefact.sha256


def test_run_eval_calls_evaluate_corpus_with_run_id(tmp_path: Path):
    _, mock_eval, _, _ = _invoke_run(tmp_path, with_eval=True, scorecards=_fake_scorecards())

    assert mock_eval.call_args.kwargs.get("run_id") == _FIXED_RUN_ID


def test_run_eval_scorecards_in_terminal_manifest(tmp_path: Path):
    """Scorecards from eval must appear in the single terminal manifest write."""
    _, _, _, out = _invoke_run(tmp_path, with_eval=True, scorecards=_fake_scorecards())

    manifest = json.loads((out / "manifest.json").read_bytes())
    assert "scorecards" in manifest, "terminal manifest must include scorecards"
    assert manifest["scorecards"]["graph"]["overall"] == "pass"


def test_run_without_eval_has_no_scorecards_in_manifest(tmp_path: Path):
    """Without --eval the manifest must not have a scorecards key."""
    result, _, _, out = _invoke_run(tmp_path, with_eval=False)

    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert manifest.get("scorecards") is None
