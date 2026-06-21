import hashlib
import time
from pathlib import Path

from codeograph.evals.models import BooleanThreshold, CheckResult

_RATIONALE = (
    "ADR-007 golden-graph pattern — current graph.json must byte-match the "
    "committed golden. A mismatch signals either an intentional schema change "
    "(requires --update-goldens) or an unintended regression."
)

# Goldens live at <repo_root>/tests/golden/<corpus_id>/graph.json (singular,
# per amended ADR-007 path convention). This file is 4 parents up from the
# repo root (codeograph/).
_GOLDENS_BASE = Path(__file__).parents[4] / "tests" / "golden"


def check_golden_graph_agreement(corpus_id: str, current_sha256: str) -> CheckResult:
    """Compare *current_sha256* against the committed golden for *corpus_id*.

    Both values are supplied by the caller (runner.py), which holds them in
    memory from the manifest or from the graph artefact produced by Pass 0.
    The check itself performs no I/O on the manifest — it only reads the
    committed golden file.

    Skips with ``no_golden_committed`` when no golden exists for this corpus.
    """
    start_time = time.perf_counter()

    golden_path = _GOLDENS_BASE / corpus_id / "graph.json"

    if not corpus_id or not golden_path.exists():
        return CheckResult(
            id="golden_graph_agreement",
            category="graph",
            result="skip",
            value=None,
            threshold=BooleanThreshold(expected=True),
            rationale=_RATIONALE,
            duration_ms=int((time.perf_counter() - start_time) * 1000),
            details={
                "skip_reason": "no_golden_committed",
                "corpus_id": corpus_id,
                "expected_golden_path": str(golden_path),
            },
        )

    golden_sha256 = hashlib.sha256(golden_path.read_bytes()).hexdigest()
    value = current_sha256 == golden_sha256

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    return CheckResult(
        id="golden_graph_agreement",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale=_RATIONALE,
        duration_ms=duration_ms,
        details={
            "corpus_id": corpus_id,
            "current_sha256": current_sha256,
            "golden_sha256": golden_sha256,
            "golden_path": str(golden_path),
        },
    )
