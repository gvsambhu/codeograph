"""Unit tests for codeograph/evals/checks/code/compile.py (ADR-017 Fork 4/6)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from codeograph.evals.checks.code.compile import check_compile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(out_dir: Path, sidecar_meta: dict | None = None) -> None:
    """Write a minimal manifest.json with optional compile_checks pointer."""
    artefacts: dict = {
        "graph": {"path": "graph.json", "schema_version": "1.0.0", "sha256": "a" * 64},
        "llm_annotations": {"path": "llm-annotations.json", "schema_version": "1.0.0", "sha256": None},
    }
    if sidecar_meta:
        artefacts["compile_checks"] = {"ts": sidecar_meta}
    manifest = {
        "schema_version": "1.6.0",
        "codeograph_version": "0.1.0",
        "source_path": str(out_dir),
        "corpus_id": "test-corpus",
        "artefacts": artefacts,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_sidecar(out_dir: Path, checks: list[dict]) -> tuple[Path, str]:
    """Write compile-checks.ts.json and return (path, sha256)."""
    evals_dir = out_dir / "evals"
    evals_dir.mkdir(exist_ok=True)
    sidecar = {"schema_version": "1.0.0", "target": "ts", "renderer_version": "0.1.0", "checks": checks}
    content = json.dumps(sidecar).encode("utf-8")
    path = evals_dir / "compile-checks.ts.json"
    path.write_bytes(content)
    return path, hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Skip paths
# ---------------------------------------------------------------------------


def test_compile_skip_when_no_manifest_entry(tmp_path: Path):
    """No compile_checks in manifest → skip with sidecar_missing_or_corrupt."""
    _write_manifest(tmp_path)  # no sidecar_meta
    result = check_compile(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "compile_checks_sidecar_missing_or_corrupt"


def test_compile_skip_when_sidecar_file_missing(tmp_path: Path):
    """Manifest has pointer but file doesn't exist → skip."""
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": "a" * 64})
    result = check_compile(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "compile_checks_sidecar_missing_or_corrupt"


def test_compile_skip_when_sha256_mismatch(tmp_path: Path):
    """Sidecar exists but sha256 in manifest is wrong → skip (tamper detected)."""
    _, real_sha = _write_sidecar(tmp_path, [])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": "b" * 64})
    result = check_compile(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "compile_checks_sidecar_missing_or_corrupt"


def test_compile_skip_all_preflight(tmp_path: Path):
    """All checks need a tool that's not on PATH → slot skip preflight_missing_tool."""
    _, sha = _write_sidecar(tmp_path, [
        {"name": "tsc", "cmd": ["npx", "tsc"], "workdir": ".",
         "required_tools": ["definitely-not-on-path-xyz"], "pass_on_exit_codes": [0]},
    ])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})
    result = check_compile(tmp_path, "ts")
    assert result.result == "skip"
    assert result.details["skip_reason"] == "preflight_missing_tool"


# ---------------------------------------------------------------------------
# Pass / fail paths (mock subprocess)
# ---------------------------------------------------------------------------


def _make_completed(returncode: int, stdout: str = "", stderr: str = "") -> object:
    """Return a mock CompletedProcess-like object."""
    class _R:
        pass
    r = _R()
    r.returncode = returncode  # type: ignore[attr-defined]
    r.stdout = stdout  # type: ignore[attr-defined]
    r.stderr = stderr  # type: ignore[attr-defined]
    return r


def test_compile_pass_when_all_checks_pass(tmp_path: Path):
    """All checks return exit code 0 → value=1.0."""
    _, sha = _write_sidecar(tmp_path, [
        {"name": "tsc", "cmd": ["tsc", "--noEmit"], "workdir": ".",
         "required_tools": [], "pass_on_exit_codes": [0]},
    ])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})
    with patch("subprocess.run", return_value=_make_completed(0, "OK", "")):
        result = check_compile(tmp_path, "ts")
    assert result.result == "pass"
    assert result.value == 1.0


def test_compile_fail_when_check_fails(tmp_path: Path):
    """A check returns non-zero → value < 1.0, result fail."""
    _, sha = _write_sidecar(tmp_path, [
        {"name": "tsc", "cmd": ["tsc"], "workdir": ".",
         "required_tools": [], "pass_on_exit_codes": [0]},
        {"name": "lint", "cmd": ["lint"], "workdir": ".",
         "required_tools": [], "pass_on_exit_codes": [0]},
    ])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})

    side_effects = [_make_completed(0), _make_completed(1, stderr="error")]
    with patch("subprocess.run", side_effect=side_effects):
        result = check_compile(tmp_path, "ts")
    assert result.result == "fail"
    assert result.value == pytest.approx(0.5)


def test_compile_pass_with_mixed_preflight_skip_and_run(tmp_path: Path):
    """One check runs and passes; one is preflight-skipped → pass, value from ran checks."""
    _, sha = _write_sidecar(tmp_path, [
        {"name": "tsc", "cmd": ["tsc"], "workdir": ".",
         "required_tools": [], "pass_on_exit_codes": [0]},
        {"name": "go_build", "cmd": ["go", "build"], "workdir": ".",
         "required_tools": ["definitely-not-on-path-xyz"], "pass_on_exit_codes": [0]},
    ])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})
    with patch("subprocess.run", return_value=_make_completed(0)):
        result = check_compile(tmp_path, "ts")
    assert result.result == "pass"
    assert result.value == 1.0
    assert "go_build" in result.details["skipped_checks"]


def test_compile_timeout_counts_as_fail(tmp_path: Path):
    """Subprocess timeout → check fails with timeout flag."""
    import subprocess as sp
    _, sha = _write_sidecar(tmp_path, [
        {"name": "tsc", "cmd": ["tsc"], "workdir": ".",
         "required_tools": [], "pass_on_exit_codes": [0]},
    ])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})
    exc = sp.TimeoutExpired(cmd=["tsc"], timeout=120)
    exc.stdout = b""
    exc.stderr = b""
    with patch("subprocess.run", side_effect=exc):
        result = check_compile(tmp_path, "ts")
    assert result.result == "fail"
    assert result.details["check_results"][0]["timeout"] is True  # type: ignore[index]


def test_compile_empty_sidecar_passes(tmp_path: Path):
    """Sidecar with no checks → value=1.0 (nothing to fail)."""
    _, sha = _write_sidecar(tmp_path, [])
    _write_manifest(tmp_path, {"path": "evals/compile-checks.ts.json", "sha256": sha})
    result = check_compile(tmp_path, "ts")
    assert result.result == "pass"
    assert result.value == 1.0
