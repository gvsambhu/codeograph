import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from codeograph.evals.scorecard_schema import CheckResult, MinRatioThreshold

_RATIONALE = (
    "FR-7 — compile is the minimum bar for generated code; ADR-008 Fork 3 supplies "
    "the per-renderer check list; aggregation is sharp because any failure indicates "
    "a renderer bug (ADR-017 Fork 4)."
)
_TIMEOUT_S = 120
_TAIL_LINES = 100


def check_compile(output_dir: Path, target: str) -> CheckResult:
    """Aggregate compile checks for a rendered target per ADR-017 Fork 4/6.

    Reads the compile-checks sidecar from the manifest pointer, verifies its
    sha256, then runs each check sequentially: preflight tool presence, then
    subprocess with a 120s timeout. Full output is written to a per-check log
    file; the last 100 lines are embedded in details.
    """
    start_time = time.perf_counter()

    def _elapsed() -> int:
        return int((time.perf_counter() - start_time) * 1000)

    # ------------------------------------------------------------------ #
    # 1. Read manifest — locate sidecar via pointer
    # ------------------------------------------------------------------ #
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    compile_checks_map = manifest.get("artefacts", {}).get("compile_checks", {})
    sidecar_meta = compile_checks_map.get(target)

    if sidecar_meta is None:
        return CheckResult(
            id="compile",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=1.0),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "compile_checks_sidecar_missing_or_corrupt",
                "target": target,
                "reason": "no compile_checks entry in manifest for this target",
            },
        )

    # ------------------------------------------------------------------ #
    # 2. Verify sidecar sha256 (tamper-evidence per ADR-017 Fork 8)
    # ------------------------------------------------------------------ #
    sidecar_path = output_dir / sidecar_meta["path"]
    if not sidecar_path.exists():
        return CheckResult(
            id="compile",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=1.0),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "compile_checks_sidecar_missing_or_corrupt",
                "target": target,
                "reason": f"sidecar file not found: {sidecar_path}",
            },
        )

    sidecar_bytes = sidecar_path.read_bytes()
    actual_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()
    if actual_sha256 != sidecar_meta.get("sha256", ""):
        return CheckResult(
            id="compile",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=1.0),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "compile_checks_sidecar_missing_or_corrupt",
                "target": target,
                "reason": "sha256 mismatch — sidecar may have been modified after render",
                "expected_sha256": sidecar_meta.get("sha256"),
                "actual_sha256": actual_sha256,
            },
        )

    # ------------------------------------------------------------------ #
    # 3. Parse sidecar and run checks sequentially (ADR-017 Fork 6)
    # ------------------------------------------------------------------ #
    sidecar = json.loads(sidecar_bytes)
    checks = sidecar.get("checks", [])
    check_results: list[dict[str, object]] = []
    preflight_skips: list[str] = []

    for check in checks:
        name: str = check["name"]
        cmd: list[str] = check["cmd"]
        pass_on_exit_codes: list[int] = check.get("pass_on_exit_codes", [0])
        required_tools: list[str] = check.get("required_tools", [])

        # Resolve workdir: relative to <output_dir>/<target>/
        raw_workdir = check.get("workdir", ".")
        workdir = (output_dir / target / raw_workdir).resolve()

        # Preflight: all required tools must be on PATH
        missing_tools = [t for t in required_tools if shutil.which(t) is None]
        if missing_tools:
            preflight_skips.append(name)
            check_results.append(
                {
                    "name": name,
                    "status": "preflight_skip",
                    "missing_tools": missing_tools,
                }
            )
            continue

        # Execute with timeout; continue regardless of result (Fork 6)
        log_path = output_dir / "evals" / f"{target}-scorecard.compile.{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir if workdir.exists() else output_dir,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_S,
            )
            exit_code: int | None = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")

        # Write full log regardless of outcome
        log_path.write_text(
            f"CMD: {cmd}\nWORKDIR: {workdir}\nEXIT: {exit_code}\nTIMEOUT: {timed_out}\n"
            f"\n=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}",
            encoding="utf-8",
        )

        passed = (not timed_out) and (exit_code in pass_on_exit_codes)
        stdout_tail = "\n".join(stdout.splitlines()[-_TAIL_LINES:])
        stderr_tail = "\n".join(stderr.splitlines()[-_TAIL_LINES:])

        check_results.append(
            {
                "name": name,
                "status": "pass" if passed else "fail",
                "exit_code": exit_code,
                "timeout": timed_out,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
                "log_path": str(log_path),
            }
        )

    # ------------------------------------------------------------------ #
    # 4. Aggregate per ADR-017 Fork 4 rules
    # ------------------------------------------------------------------ #
    ran = [r for r in check_results if r["status"] != "preflight_skip"]
    passed_ran = [r for r in ran if r["status"] == "pass"]

    # All checks skipped via preflight → slot skip
    if not ran and preflight_skips:
        missing: list[str] = []
        for r in check_results:
            if r["status"] == "preflight_skip":
                tools = r.get("missing_tools")
                if isinstance(tools, list):
                    missing.extend(str(t) for t in tools)
        return CheckResult(
            id="compile",
            category="code",
            result="skip",
            value=None,
            threshold=MinRatioThreshold(pass_at_or_above=1.0),
            rationale=_RATIONALE,
            duration_ms=_elapsed(),
            details={
                "skip_reason": "preflight_missing_tool",
                "missing_tools": list(set(missing)),
                "check_results": check_results,
            },
        )

    # Empty sidecar → treat as pass (nothing to check)
    if not check_results:
        value: float = 1.0
    elif not ran:
        value = 1.0
    else:
        value = len(passed_ran) / len(ran)

    return CheckResult(
        id="compile",
        category="code",
        value=value,
        threshold=MinRatioThreshold(pass_at_or_above=1.0),
        rationale=_RATIONALE,
        duration_ms=_elapsed(),
        details={
            "check_results": check_results,
            "skipped_checks": preflight_skips,
            "passed": len(passed_ran),
            "ran": len(ran),
            "total": len(check_results),
        },
    )
