from pathlib import Path


def display_path(path: str | Path, *, base: Path | None = None) -> str:
    """Render *path* as a portable, anchor-relative POSIX string.

    Committed scorecards must not embed absolute host filesystem paths: they
    leak the local home directory and differ across machines/CI, so a scorecard
    captured on one box never matches one captured on another. This renders
    *path* relative to *base* when it sits underneath it, else relative to the
    current working directory, else as the bare file/dir name — always with
    forward slashes so Windows and Linux emit byte-identical strings.

    Used only for the path values emitted into ``CheckResult.details``; checks
    keep the original absolute path for their own filesystem operations.
    """
    if not path:
        return ""
    p = Path(path)
    for anchor in (base, Path.cwd()):
        if anchor is None:
            continue
        try:
            return p.resolve().relative_to(anchor.resolve()).as_posix()
        except ValueError:
            continue
    return p.name
