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
from pathlib import Path

import click

from codeograph.cli.eval_report import report_cmd
from codeograph.evals.runner import EvalRunner, MissingOutputError


class MutuallyExclusiveOption(click.Option):
    def __init__(self, *args, **kwargs) -> None:
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        help_text = kwargs.get("help", "")
        if self.mutually_exclusive:
            ex_str = ", ".join(self.mutually_exclusive)
            kwargs["help"] = help_text + f" (Mutually exclusive with: {ex_str})"
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with "
                f"arguments `{', '.join(self.mutually_exclusive)}`."
            )
        return super().handle_parse_result(ctx, opts, args)


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

        has_failure = any(
            any(c.result == "fail" for c in s.checks)
            for s in scorecards
        )

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
