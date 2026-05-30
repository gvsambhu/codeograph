"""Generate the JSON Schema for the scorecard framework."""

import json
from pathlib import Path

from codeograph.evals.scorecard_schema import Scorecard


def main():
    schema = Scorecard.model_json_schema()
    
    out_path = Path(__file__).parent.parent / "codeograph" / "evals" / "scorecard.schema.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")
        
    print(f"Wrote JSON Schema to {out_path}")

if __name__ == "__main__":
    main()
