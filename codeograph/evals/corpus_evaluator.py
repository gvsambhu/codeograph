"""
CorpusEvaluator — thin bridge between the run pipeline and run_evals.

In the ``run --eval`` path, the run pipeline supplies corpus context
in-memory (corpus_id, run_id, codeograph_version, graph_sha256) so
run_evals can execute without needing manifest.json on disk. The caller
(cli/main.py) then passes the returned scorecard pointers to the
ManifestAssembler for the single terminal write.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from codeograph.evals.runner import MissingOutputError, run_evals
from codeograph.manifest.models import ScorecardPointer

logger = logging.getLogger(__name__)


def evaluate_corpus(
    out_dir: Path,
    *,
    corpus_id: str | None = None,
    run_id: str | None = None,
    codeograph_version: str | None = None,
    graph_sha256: str | None = None,
) -> dict[str, ScorecardPointer]:
    """Run scorecard evaluations against *out_dir*; return scorecard pointers.

    Context params are forwarded to ``run_evals``. When all four are
    provided (the ``run --eval`` path), no manifest read is performed.
    When any is absent (standalone ``eval run`` path), ``run_evals``
    reads the manifest itself.

    Manifest patching is NOT performed here — the caller is responsible:
    - ``run --eval``: cli/main.py passes pointers to the ManifestAssembler.
    - standalone ``eval run``: cli/eval.py patches the manifest after this call.

    :raises SystemExit(2): If the output directory or manifest is missing.
    """
    click.echo("Running evaluation (--eval requested)...")
    try:
        kinds = ["graph"]
        for child in out_dir.iterdir():
            if child.is_dir() and child.name not in ("evals", ".codeograph"):
                kinds.append(child.name)

        _, scorecard_pointers = run_evals(
            output_dir=out_dir,
            scorecard_kinds=kinds,
            corpus_id=corpus_id,
            run_id=run_id,
            codeograph_version=codeograph_version,
            graph_sha256=graph_sha256,
        )
        return scorecard_pointers
    except MissingOutputError as e:
        click.echo(f"Eval Error: {e}", err=True)
        sys.exit(2)
