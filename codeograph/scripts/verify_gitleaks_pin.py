#!/usr/bin/env python3
import sys
import re
from pathlib import Path

def get_git_root() -> Path:
    # This script is at codeograph/codeograph/scripts/verify_gitleaks_pin.py
    # Outer root is codeograph/
    return Path(__file__).resolve().parents[2]

def main() -> int:
    root = get_git_root()
    secrets_scan_path = root / ".github" / "workflows" / "secrets-scan.yml"
    pre_commit_path = root / ".pre-commit-config.yaml"
    nightly_path = root / ".github" / "workflows" / "nightly.yml"

    # 1. Parse secrets-scan.yml
    if not secrets_scan_path.exists():
        print(f"Error: secrets-scan.yml not found at {secrets_scan_path}", file=sys.stderr)
        return 1
    
    secrets_scan_content = secrets_scan_path.read_text(encoding="utf-8")
    # Match pattern: GITLEAKS_VERSION: "8.30.1"
    scan_match = re.search(r"GITLEAKS_VERSION:\s*[\"']?([0-9a-zA-Z\.-]+)[\"']?", secrets_scan_content)
    if not scan_match:
        print("Error: Could not find GITLEAKS_VERSION pin in secrets-scan.yml", file=sys.stderr)
        return 1
    secrets_scan_version = scan_match.group(1).lstrip('v')

    # 2. Parse .pre-commit-config.yaml
    if not pre_commit_path.exists():
        print(f"Error: .pre-commit-config.yaml not found at {pre_commit_path}", file=sys.stderr)
        return 1
    
    pre_commit_content = pre_commit_path.read_text(encoding="utf-8")
    # Find the repo block for gitleaks
    # We look for the repo url first and then find the rev line following it.
    gitleaks_repo_idx = pre_commit_content.find("https://github.com/gitleaks/gitleaks")
    if gitleaks_repo_idx == -1:
        print("Error: Could not find gitleaks repo in .pre-commit-config.yaml", file=sys.stderr)
        return 1
    
    # Extract lines after the repo declaration to find rev
    after_repo = pre_commit_content[gitleaks_repo_idx:]
    rev_match = re.search(r"rev:\s*[\"']?([0-9a-zA-Z\.-]+)[\"']?", after_repo)
    if not rev_match:
        print("Error: Could not find rev pin in gitleaks repo in .pre-commit-config.yaml", file=sys.stderr)
        return 1
    pre_commit_version = rev_match.group(1).lstrip('v')

    # 3. Parse nightly.yml (if exists, verify it too)
    nightly_version = None
    if nightly_path.exists():
        nightly_content = nightly_path.read_text(encoding="utf-8")
        nightly_match = re.search(r"GITLEAKS_VERSION:\s*[\"']?([0-9a-zA-Z\.-]+)[\"']?", nightly_content)
        if nightly_match:
            nightly_version = nightly_match.group(1).lstrip('v')

    print(f"Found Gitleaks pins:")
    print(f"  - secrets-scan.yml:       {secrets_scan_version}")
    print(f"  - .pre-commit-config.yaml: {pre_commit_version}")
    if nightly_version:
        print(f"  - nightly.yml:            {nightly_version}")

    # Check match
    mismatches = []
    if secrets_scan_version != pre_commit_version:
        mismatches.append(
            f"secrets-scan.yml ({secrets_scan_version}) != .pre-commit-config.yaml ({pre_commit_version})"
        )
    if nightly_version and secrets_scan_version != nightly_version:
        mismatches.append(
            f"secrets-scan.yml ({secrets_scan_version}) != nightly.yml ({nightly_version})"
        )

    if mismatches:
        print("\n[FAIL] Gitleaks version pin parity violation (ADR-023):", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1

    print("\n[PASS] Gitleaks version pins match.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
