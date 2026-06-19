import json
import time
from pathlib import Path

import jsonschema

from codeograph.evals.models import BooleanThreshold, CheckResult
from codeograph.graph.models.graph_schema import CodeographKnowledgeGraph

# schema_validity.py is at codeograph/evals/checks/graph/schema_validity.py
# parents[3] is codeograph/ (the Python package root containing schema/)
_GRAPH_SCHEMA_PATH = Path(__file__).parents[3] / "schema" / "graph.schema.json"


def check_schema_validity(graph: CodeographKnowledgeGraph) -> CheckResult:
    start_time = time.perf_counter()

    schema = json.loads(_GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
    graph_dict = graph.model_dump(mode="json")

    errors: list[str] = []
    try:
        jsonschema.validate(instance=graph_dict, schema=schema)
        value = True
    except jsonschema.ValidationError as exc:
        value = False
        errors.append(exc.message)

    duration_ms = int((time.perf_counter() - start_time) * 1000)

    return CheckResult(
        id="schema_validity",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale="FR-7a — schema_validity ensures the emitted graph.json strictly matches the Pydantic schema (ADR-017 Fork 3).",
        duration_ms=duration_ms,
        details={"validation_errors": errors},
    )
