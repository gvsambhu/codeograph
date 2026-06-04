"""CLI subcommands for evaluation reports (M6)."""

import click
from typing import Tuple

@click.command(name="report")
@click.argument("output_dirs", nargs=-1, type=click.Path(exists=True))
def report_cmd(output_dirs: Tuple[str, ...]) -> None:
    """Cross-corpus aggregation report."""
    if not output_dirs:
        raise click.UsageError("At least one OUTPUT_DIR is required.")
        
    click.echo(f"Generating report for {len(output_dirs)} directories...")
    # TODO: M6 learner implements Eval Report logic here
