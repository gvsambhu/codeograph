"""JSON Schema generator / freshness checker for the manifest.

Per ADR-022 Fork 7: the committed JSON Schema at
``codeograph/_generated/manifest.schema.json`` is the **external** contract
for manifest consumers (any standard JSON Schema validator: ``ajv``,
``python-jsonschema``, ``jsonschema-cli``). It is regenerated from the
Pydantic source of truth via :func:`Manifest.model_json_schema` and
pinned by a CI freshness gate that mirrors the ADR-014 prompt-freshness
pattern.

Usage::

    # Re-generate the committed JSON Schema after editing the Pydantic
    # source. Commit the regenerated file alongside the source change.
    python -m codeograph.manifest.schema_cli --generate

    # CI freshness gate: exit non-zero if the committed schema is stale
    # relative to the Pydantic source. Runs in the lint job alongside
    # the ADR-014 prompt-freshness and ADR-017 scorecard-freshness gates.
    python -m codeograph.manifest.schema_cli --check

The path is anchored at the repository root (``codeograph/_generated/``)
so the command works from any CWD.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from codeograph.manifest.schema import Manifest

# Anchored at the repository root, which is the parent of the
# ``codeograph/`` Python package directory. Resolved at call time so the
# command works regardless of CWD (CI runs from the repo root by
# convention, but contributors may invoke from elsewhere).
GENERATED_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "_generated" / "manifest.schema.json"


def _current_schema() -> dict:
    """Regenerate the JSON Schema from the Pydantic source of truth."""
    return Manifest.model_json_schema()


@click.command()
@click.option(
    "--generate",
    is_flag=True,
    help="Write the JSON Schema to codeograph/_generated/manifest.schema.json.",
)
@click.option(
    "--check",
    is_flag=True,
    help="Exit non-zero if the committed schema does not match the Pydantic source.",
)
def main(generate: bool, check: bool) -> None:
    """Generate or check the manifest JSON Schema."""
    if generate == check:
        raise click.UsageError("Exactly one of --generate or --check must be specified.")

    current = _current_schema()

    if check:
        if not GENERATED_SCHEMA_PATH.exists():
            raise click.ClickException(f"{GENERATED_SCHEMA_PATH} does not exist; regenerate with --generate")
        committed = json.loads(GENERATED_SCHEMA_PATH.read_text(encoding="utf-8"))
        if committed != current:
            raise click.ClickException(f"{GENERATED_SCHEMA_PATH} is stale; regenerate with --generate")
        return

    if generate:
        GENERATED_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_SCHEMA_PATH.write_text(
            json.dumps(current, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        click.echo(f"wrote {GENERATED_SCHEMA_PATH}")


__all__ = ["GENERATED_SCHEMA_PATH", "main"]


if __name__ == "__main__":
    main()
