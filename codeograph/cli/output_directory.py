"""Output directory resolution and safety utilities shared across CLI subcommands."""

from __future__ import annotations

import shutil
from pathlib import Path

import click

__all__ = ["prepare_output_directory"]


def prepare_output_directory(out: str, force: bool, *, clear: bool) -> Path:
    """Resolve, validate, and optionally clear an output directory.

    Raises :class:`click.UsageError` if:

    * *out* resolves to the current working directory or an ancestor of it
      (path-safety guard — avoids accidental data loss via ``--force``).
    * *out* is non-empty and *force* is ``False``.

    When *clear* is ``True`` and *force* is ``True``, all existing contents
    are removed before returning so the caller starts with an empty directory.
    When *clear* is ``False``, the directory is left untouched even if
    non-empty (the caller writes into it alongside existing files).
    """
    out_path = Path(out).resolve()

    cwd = Path.cwd().resolve()
    if out_path == cwd or cwd.is_relative_to(out_path):
        raise click.UsageError(
            f"--out '{out_path}' is the current working directory or an ancestor of it. "
            "Choose a dedicated output directory to avoid accidental data loss."
        )

    if out_path.exists() and any(out_path.iterdir()):
        if not force:
            raise click.UsageError(
                f"Output directory '{out_path}' already exists and is non-empty. Use --force to overwrite."
            )
        if clear:
            click.echo(f"Clearing existing files in {out_path} …")
            for child in out_path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

    return out_path
