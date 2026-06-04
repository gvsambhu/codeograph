"""CLI subcommands for evaluation (M7)."""

import json
import sys
import typing
from pathlib import Path

import click

from codeograph.cli.eval_report import report_cmd
from codeograph.evals.runner import EvalRunner, MissingOutputError


class MutuallyExclusiveOption(click.Option):
    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        self.mutually_exclusive = set(kwargs.pop("mutually_exclusive", []))
        help_text = kwargs.get("help", "")
        if self.mutually_exclusive:
            ex_str = ", ".join(self.mutually_exclusive)
            kwargs["help"] = help_text + f" (Mutually exclusive with: {ex_str})"
        super().__init__(*args, **kwargs)

    def handle_parse_result(
        self, ctx: click.Context, opts: typing.Mapping[str, typing.Any], args: list[str]
    ) -> tuple[typing.Any, list[str]]:
        if self.mutually_exclusive.intersection(opts) and self.name in opts:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with "
                f"arguments `{', '.join(self.mutually_exclusive)}`."
            )
        return super().handle_parse_result(ctx, opts, args)


@click.group(name="eval", invoke_without_command=True)
@click.argument("output_dir", type=click.Path(), required=False)
@click.option("--scorecard", multiple=True, help="Restrict to specific scorecards (e.g. graph, ts)")
@click.option(
    "--check",
    multiple=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["skip_check"],
    help="Run only these check IDs"
)
@click.option(
    "--skip-check",
    multiple=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["check"],
    help="Skip these check IDs"
)
@click.option(
    "--output-json",
    is_flag=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["output_md"],
    help="Output results in JSON"
)
@click.option(
    "--output-md",
    is_flag=True,
    cls=MutuallyExclusiveOption,
    mutually_exclusive=["output_json"],
    help="Output results in Markdown"
)
@click.pass_context
def eval_cli(
    ctx: click.Context, 
    output_dir: str | None, 
    scorecard: tuple[str, ...], 
    check: tuple[str, ...], 
    skip_check: tuple[str, ...], 
    output_json: bool, 
    output_md: bool
) -> None:
    """Evaluate quality of generated code and graphs."""
    if ctx.invoked_subcommand is not None:
        return

    if not output_dir:
        raise click.UsageError("Missing argument 'OUTPUT_DIR'.")

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
        
        # Check overall failure
        has_failure = any(
            any(c.result == "fail" for c in s.checks) 
            for s in scorecards
        )
        
        if output_json:
            click.echo(json.dumps([json.loads(s.model_dump_json()) for s in scorecards], indent=2))
        elif output_md:
            click.echo("# Evaluation Results (Markdown placeholder)")
        else:
            click.echo(f"Evaluated {len(scorecards)} scorecards. Overall failure: {has_failure}")
            
        if has_failure:
            sys.exit(1)
            
    except MissingOutputError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)

eval_cli.add_command(report_cmd)
