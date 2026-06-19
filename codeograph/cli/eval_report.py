"""CLI subcommand for cross-corpus evaluation reports (M6).

ADR-017 Fork 7: ``codeograph eval report <dir> [<dir> ...]``

Output flags (mutually exclusive):
  --output-md <path>    Write markdown report to file (and stdout)
  --output-json <path>  Write JSON-serialised ReportResult to file (and stdout)

When neither flag is given the markdown report is printed to stdout only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click


@click.command(name="report")
@click.argument("output_dirs", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--output-md",
    "output_md",
    default=None,
    metavar="FILE",
    help="Write the markdown report to FILE (also printed to stdout).",
)
@click.option(
    "--output-json",
    "output_json",
    default=None,
    metavar="FILE",
    help="Write the JSON-serialised ReportResult to FILE (also printed to stdout).",
)
def report_cmd(
    output_dirs: tuple[str, ...],
    output_md: str | None,
    output_json: str | None,
) -> None:
    """Cross-corpus aggregation report across one or more OUTPUT_DIRS."""
    if not output_dirs:
        raise click.UsageError("At least one OUTPUT_DIR is required.")

    if output_md and output_json:
        raise click.UsageError("--output-md and --output-json are mutually exclusive.")

    from codeograph.evals.report import generate_report, render_markdown

    paths = [Path(p) for p in output_dirs]
    report = generate_report(paths)

    if output_json:
        json_str = json.dumps(json.loads(report.model_dump_json()), indent=2)
        click.echo(json_str)
        Path(output_json).write_text(json_str, encoding="utf-8")
    else:
        md = render_markdown(report)
        click.echo(md)
        if output_md:
            Path(output_md).write_text(md, encoding="utf-8")

    if report.overall != "pass":
        sys.exit(1)
