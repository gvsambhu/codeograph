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

from codeograph.manifest.models import Manifest

# Anchored at the repository root, which is the parent of the
# ``codeograph/`` Python package directory. Resolved at call time so the
# command works regardless of CWD (CI runs from the repo root by
# convention, but contributors may invoke from elsewhere).
GENERATED_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "_generated" / "manifest.schema.json"


def _current_schema() -> dict[str, object]:
    """Regenerate the JSON Schema from the Pydantic source of truth."""
    schema = Manifest.model_json_schema()
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}


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
@click.option(
    "--schema-path",
    type=click.Path(path_type=Path),
    default=GENERATED_SCHEMA_PATH,
    help="Schema file to check or write (default: the committed one).",
)
def main(generate: bool, check: bool, schema_path: Path = GENERATED_SCHEMA_PATH) -> None:
    """Generate or check the manifest JSON Schema."""
    if generate == check:
        raise click.UsageError("Exactly one of --generate or --check must be specified.")

    current = _current_schema()

    if check:
        if not schema_path.exists():
            raise click.ClickException(f"{schema_path} does not exist; regenerate with --generate")
        committed = json.loads(schema_path.read_text(encoding="utf-8"))
        if committed != current:
            raise click.ClickException(f"{schema_path} is stale; regenerate with --generate")
        return

    if generate:
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(
            json.dumps(current, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="",
        )
        click.echo(f"wrote {schema_path}")


__all__ = ["GENERATED_SCHEMA_PATH", "main"]


if __name__ == "__main__":
    main()
