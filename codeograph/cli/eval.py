"""CLI subcommands for evaluation (M7).

Command surface (ADR-017 Fork 5 + Fork 7):

    codeograph eval run  <output_dir>          # single-corpus scorecard
    codeograph eval report <dir> [<dir> ...]   # cross-corpus aggregation

The previous design used a Click group with an optional positional argument
AND a subcommand, which Click cannot disambiguate: ``eval report <dir>``
parsed ``report`` as the positional argument.  The fix splits into two
explicit subcommands with no group-level positional argument.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import click

from codeograph.cli.eval_report import report_cmd
from codeograph.cli.mutually_exclusive_option import MutuallyExclusiveOption
from codeograph.evals.runner import EvalRunner, MissingOutputError
from codeograph.manifest.io import read as manifest_io_read



# ---------------------------------------------------------------------------
# eval run — single-corpus scorecard
# ---------------------------------------------------------------------------


@click.command(name="run")
@click.argument("output_dir", type=click.Path())
@click.option("--scorecard", multiple=True, help="Restrict to specific scorecards (e.g. graph, ts)")
@click.option(
    "--check",
    multiple=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["skip_check"],
    help="Run only these check IDs",
)
@click.option(
    "--skip-check",
    multiple=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["check"],
    help="Skip these check IDs",
)
def run_cmd(
    output_dir: str,
    scorecard: tuple[str, ...],
    check: tuple[str, ...],
    skip_check: tuple[str, ...],
) -> None:
    """Evaluate quality of generated code and graphs for OUTPUT_DIR."""
    runner = EvalRunner()

    try:
        manifest_path = Path(output_dir) / "manifest.json"
        if not manifest_path.exists():
            click.echo(f"Error: manifest.json missing in {output_dir}", err=True)
            sys.exit(2)

        # Read the manifest via manifest_io (lenient on unknown top-level
        # fields, strict on present fields). The run_id is surfaced in the
        # log so the user can correlate the eval result with the original
        # run that produced the manifest (ADR-022 Fork 4 contract).
        # EvalRunner re-reads the manifest internally for its own use; the
        # read here is for log visibility, not for passing data.
        try:
            manifest = manifest_io_read(manifest_path)
        except Exception as exc:
            click.echo(f"Error: could not read manifest.json ({exc})", err=True)
            sys.exit(2)
        click.echo(f"Evaluating run {manifest.run_id}...")

        # Default to all rendered targets + graph if --scorecard not provided
        if not scorecard:
            kinds = ["graph"]
            for child in Path(output_dir).iterdir():
                if child.is_dir() and child.name not in ("evals", ".codeograph"):
                    kinds.append(child.name)
            scorecard = tuple(kinds)

        scorecards = runner.run(
            output_dir=Path(output_dir),
            scorecard_kinds=list(scorecard),
            check_filter=list(check) if check else None,
            skip_checks=list(skip_check) if skip_check else None,
        )

        has_failure = any(any(c.result == "fail" for c in s.checks) for s in scorecards)

        click.echo(json.dumps([json.loads(s.model_dump_json()) for s in scorecards], indent=2))

        if has_failure:
            sys.exit(1)

    except MissingOutputError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


# ---------------------------------------------------------------------------
# eval group — top-level dispatcher
# ---------------------------------------------------------------------------


@click.group(name="eval")
def eval_cli() -> None:
    """Evaluate quality of generated code and graphs."""


eval_cli.add_command(run_cmd)
eval_cli.add_command(report_cmd)
