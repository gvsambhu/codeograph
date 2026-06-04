"""CLI subcommands for evaluation reports (M6)."""

import click
from typing import Tuple

@click.command(name="report")
@click.argument("output_dirs", nargs=-1, type=click.Path(exists=True))
def report_cmd(output_dirs: Tuple[str, ...]) -> None:
    """Cross-corpus aggregation report."""
    if not output_dirs:
        raise click.UsageError("At least one OUTPUT_DIR is required.")
        
    import sys
    import json
    from pathlib import Path
    from codeograph.evals.report import EvalReport

    # Evaluate all valid output_dirs
    paths = [Path(p) for p in output_dirs]
    report = EvalReport.generate(paths)
    
    # Render markdown and print
    md = EvalReport.render_markdown(report)
    click.echo(md)
    
    if report.overall != "pass":
        sys.exit(1)
