"""Fail if a committed file points at something a reader cannot open.

Two checks, both guarding the same promise: a path written in this repository
must resolve for someone who has only cloned this repository.

1. **Broken relative links.** A markdown link whose target does not exist in the
   repo. This is the general case — the target may be a bare filename, a
   relative path, or a path into a private sibling directory; all of them render
   as clickable and all of them 404.

2. **Private workspace paths.** Prose or code references to ``work/``, ``plan/``
   or ``archive/`` — sibling directories of the repo root that are not committed.
   These are usually not written as links, so check 1 does not see them.

Both have happened, repeatedly, so this is a gate rather than a convention. It
runs over staged files in pre-commit and over the whole tree in CI.

Usage::

    python scripts/check_no_workspace_refs.py            # whole tree (CI)
    python scripts/check_no_workspace_refs.py FILE...    # named files (pre-commit)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Markdown inline links and images: [text](target) / ![alt](target).
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# A private-directory reference: the name followed by a separator. Guarded on the
# left so "framework/", "workflows/", "network/" do not match, and on the right so
# bare prose ("the work we did") does not either.
WORKSPACE_PATH = re.compile(
    r"(?<![\w.-])(?:\.\./)*(work|plan|archive)/[\w./*-]", re.IGNORECASE
)

# Link targets that are not repo paths.
EXTERNAL_SCHEME = re.compile(r"^(https?:|mailto:|ftp:|tel:|data:|#)", re.IGNORECASE)

# Paths exempt from scanning, relative to the repo root.
EXEMPT_PATHS = frozenset({"scripts/check_no_workspace_refs.py"})

# Substrings that make a workspace-path match a false positive.
# "plan/execute/assemble" is a two-phase API name in ADR-008, not a directory.
EXEMPT_SUBSTRINGS = ("plan/execute",)

TEXT_SUFFIXES = frozenset(
    {
        ".md", ".py", ".txt", ".yml", ".yaml", ".toml", ".json", ".cfg",
        ".ini", ".sh", ".ps1", ".j2", ".java", ".ts",
    }
)


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / line for line in out.stdout.splitlines() if line]


def should_scan(path: Path) -> bool:
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return False
    if rel in EXEMPT_PATHS:
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def check_links(path: Path, text: str) -> list[tuple[int, str, str]]:
    """Markdown links whose target does not exist in the repo."""
    if path.suffix.lower() != ".md":
        return []
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in LINK.finditer(line):
            target = match.group(1)
            if EXTERNAL_SCHEME.match(target):
                continue
            target = target.split("#", 1)[0]  # drop any anchor
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                hits.append((lineno, f"link target does not exist: {target}", line.strip()))
    return hits


def check_workspace_paths(text: str) -> list[tuple[int, str, str]]:
    """References to private sibling directories."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if any(s in line for s in EXEMPT_SUBSTRINGS):
            continue
        match = WORKSPACE_PATH.search(line)
        if match:
            hits.append((lineno, f"private workspace path: {match.group(0)}", line.strip()))
    return hits


def main(argv: list[str]) -> int:
    candidates = [Path(a).resolve() for a in argv] if argv else tracked_files()

    failures: list[tuple[str, int, str, str]] = []
    for path in candidates:
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, reason, line in check_links(path, text) + check_workspace_paths(text):
            failures.append((rel, lineno, reason, line))

    if not failures:
        return 0

    print("Committed files must not point at things a reader cannot open.\n")
    for rel, lineno, reason, line in sorted(failures):
        print(f"  {rel}:{lineno} — {reason}")
        print(f"    {line[:120]}")
    print(
        "\nA path written here must resolve for someone who has only cloned this\n"
        "repository. `work/`, `plan/` and `archive/` are not part of it. Inline the\n"
        "content, describe it without a path, or drop the reference."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
