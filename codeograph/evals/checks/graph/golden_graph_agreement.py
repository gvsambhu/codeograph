import hashlib
import json
import time
from pathlib import Path

from codeograph.evals.models import BooleanThreshold, CheckResult

_RATIONALE = (
    "ADR-007 golden-graph pattern — current graph.json must byte-match the "
    "committed golden. A mismatch signals either an intentional schema change "
    "(requires --update-goldens) or an unintended regression."
)

# Goldens live at <repo_root>/tests/goldens/<corpus_id>/graph.json.
# This file is at codeograph/evals/checks/graph/golden_graph_agreement.py,
# so parents[4] is the repo root (codeograph/).
_GOLDENS_BASE = Path(__file__).parents[4] / "tests" / "goldens"


def check_golden_graph_agreement(output_dir: Path) -> CheckResult:
    """Compare the current graph.json sha256 against the committed golden.

    Skips with no_golden_committed when no golden exists for this corpus_id.
    corpus_id is read from manifest.json (added in manifest schema 1.6.0).
    """
    start_time = time.perf_counter()

    # ------------------------------------------------------------------ #
    # 1. Read corpus_id and current graph sha256 from the manifest
    # ------------------------------------------------------------------ #
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    corpus_id = manifest.get("corpus_id", "")
    current_sha256 = manifest["artefacts"]["graph"]["sha256"]

    # ------------------------------------------------------------------ #
    # 2. Locate the committed golden
    # ------------------------------------------------------------------ #
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

    # ------------------------------------------------------------------ #
    # 3. Compute golden sha256 and compare
    # ------------------------------------------------------------------ #
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
