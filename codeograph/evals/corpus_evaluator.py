"""
CorpusEvaluator — orchestrates evaluation of a corpus and maps check outcomes to scorecard pointers.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import click

from codeograph.evals.runner import run_evals, MissingOutputError
from codeograph.manifest.models import ScorecardPointer

logger = logging.getLogger(__name__)


"""Runs scorecard verification checks on a generated output directory.

Stateless service class.
"""

def evaluate_corpus(out_dir: Path) -> dict[str, ScorecardPointer]:
    """Runs the deterministic scorecard evaluations against out_dir.

    :param out_dir: Directory containing graph.json and other generated assets.
    :returns:       A dictionary mapping scorecard kinds (e.g. 'graph', 'typescript')
                    to ScorecardPointer schemas.
    :raises click.ClickException: If evaluation fails or missing output is encountered.
    """
    click.echo("Running evaluation (--eval requested)...")
    try:
        runner = EvalRunner()
        kinds = ["graph"]
        for child in out_dir.iterdir():
            if child.is_dir() and child.name not in ("evals", ".codeograph"):
                kinds.append(child.name)
        scorecard_models = runner.run(
            output_dir=out_dir,
            scorecard_kinds=kinds,
        )

        scorecards = {}
        for sc in scorecard_models:
            sc_filename = "graph-scorecard.json" if sc.kind == "graph" else f"{sc.kind}-scorecard.json"
            sc_path = out_dir / "evals" / sc_filename
            if sc_path.exists():
                sc_sha = hashlib.sha256(sc_path.read_bytes()).hexdigest()
            else:
                sc_sha = "0" * 64
            overall = "pass" if all(c.result in ("pass", "skip") for c in sc.checks) else "fail"
            scorecards[sc.kind] = ScorecardPointer(
                path=f"evals/{sc_filename}",
                sha256=sc_sha,
                overall=overall,
            )

        has_failure = any(c.result == "fail" for sc in scorecard_models for c in sc.checks)
        if has_failure:
            click.echo("Evaluation failed overall.")
            sys.exit(1)
        return scorecards
    except MissingOutputError as e:
        click.echo(f"Eval Error: {e}", err=True)
        sys.exit(2)
