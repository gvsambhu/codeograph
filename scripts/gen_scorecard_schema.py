"""Generate (or verify freshness of) the JSON Schema for the scorecard framework.

Usage
-----
Generate and write::

    python scripts/gen_scorecard_schema.py

Check freshness (CI gate, ADR-017 D-017-2)::

    python scripts/gen_scorecard_schema.py --check

The ``--check`` mode exits non-zero if the committed schema has drifted
from the Pydantic source without updating the file. It does not write
any files, making it safe to run in CI.
"""

import argparse
import json
import sys
from pathlib import Path

_OUT_PATH = Path(__file__).parent.parent / "codeograph" / "evals" / "scorecard.schema.json"


def _generate() -> str:
    from codeograph.evals.models import Scorecard

    schema = Scorecard.model_json_schema()
    return json.dumps(schema, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed schema is stale; do not write.",
    )
    args = parser.parse_args()

    fresh = _generate()

    if args.check:
        if not _OUT_PATH.exists():
            print(f"ERROR: {_OUT_PATH} is missing — run gen_scorecard_schema.py to create it.", file=sys.stderr)
            sys.exit(1)
        committed = _OUT_PATH.read_text(encoding="utf-8")
        if fresh != committed:
            print(
                f"ERROR: {_OUT_PATH} is stale.\n"
                f"  Run:  python scripts/gen_scorecard_schema.py\n"
                f"  Then: git add {_OUT_PATH} && git commit",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"OK: {_OUT_PATH} is up to date.")
    else:
        _OUT_PATH.write_text(fresh, encoding="utf-8")
        print(f"Wrote JSON Schema to {_OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
