import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from codeograph.evals.scorecard_schema import BooleanThreshold, CheckResult

_RATIONALE = (
    "ADR-007 §8 reproducibility envelope — three consecutive --ast-only runs on "
    "the same source must produce byte-identical graph.json (canonical-form sha256 "
    "comparison). Non-determinism breaks golden-graph regression tests."
)
_RUNS = 3


def check_reproducibility(output_dir: Path) -> CheckResult:
    """Run --ast-only against the recorded source_path three times and compare
    the canonical-form sha256 of each graph.json.

    Skip with source_path_unavailable if the source is no longer on disk.
    Fail if any subprocess run crashes (Option A — a crash is a reproducibility
    failure, not a missing-source skip).
    """
    start_time = time.perf_counter()

    # ------------------------------------------------------------------ #
    # 1. Read source_path from the manifest
    # ------------------------------------------------------------------ #
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    source_path = manifest.get("source_path", "")

    # ------------------------------------------------------------------ #
    # 2. Skip if source not recorded or no longer on disk
    # ------------------------------------------------------------------ #
    if not source_path or not Path(source_path).exists():
        return CheckResult(
            id="reproducibility",
            category="graph",
            result="skip",
            value=None,
            threshold=BooleanThreshold(expected=True),
            rationale=_RATIONALE,
            duration_ms=int((time.perf_counter() - start_time) * 1000),
            details={
                "skip_reason": "source_path_unavailable",
                "source_path": source_path,
            },
        )

    # ------------------------------------------------------------------ #
    # 3. Run --ast-only three times; collect sha256 from each manifest
    # ------------------------------------------------------------------ #
    hashes: list[str] = []
    failed_runs: list[dict[str, object]] = []

    for run_index in range(_RUNS):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "codeograph",
                    "run",
                    source_path,
                    "--out",
                    tmp,
                    "--ast-only",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                failed_runs.append(
                    {
                        "run": run_index + 1,
                        "returncode": result.returncode,
                        "stderr_tail": result.stderr[-500:] if result.stderr else "",
                    }
                )
                continue

            run_manifest_path = Path(tmp) / "manifest.json"
            if not run_manifest_path.exists():
                failed_runs.append(
                    {
                        "run": run_index + 1,
                        "returncode": result.returncode,
                        "stderr_tail": "manifest.json not found after --ast-only run",
                    }
                )
                continue

            run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
            sha256 = run_manifest["artefacts"]["graph"]["sha256"]
            hashes.append(sha256)

    # ------------------------------------------------------------------ #
    # 4. Option A: any failed run → fail (crash == non-reproducibility)
    # ------------------------------------------------------------------ #
    if failed_runs:
        value = False
        details: dict[str, object] = {
            "failed_runs": failed_runs,
            "successful_hashes": hashes,
            "source_path": source_path,
        }
    else:
        # All three ran — check hash agreement
        value = len(set(hashes)) == 1
        details = {
            "hashes": hashes,
            "all_identical": value,
            "source_path": source_path,
        }

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    return CheckResult(
        id="reproducibility",
        category="graph",
        value=value,
        threshold=BooleanThreshold(expected=True),
        rationale=_RATIONALE,
        duration_ms=duration_ms,
        details=details,
    )
