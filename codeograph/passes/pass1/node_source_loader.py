from pathlib import Path
from typing import Any

__all__ = ["NodeSourceLoader"]


class NodeSourceLoader:
    """Reads real Java source text from disk and injects it into class-like graph nodes.

    ADR-005 requires Pass 1's per-class LLM call to include the class source body,
    but graph nodes only ever carry `source_file` (a corpus-relative path) and
    `line_range` (1-indexed, inclusive — JavaParser's Range.begin.line/end.line);
    the literal source text was never populated anywhere in the pipeline before
    this loader (2026-07-06 manual-run finding).
    """

    def __init__(self, corpus_root: Path) -> None:
        self._corpus_root = corpus_root

    def load(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Populate `source_code` in place for each node with a resolvable `source_file`.

        Falls back to the whole file when `line_range` is absent or is the
        regex-fallback placeholder `[0, 0]` (ADR-003 D-003-x — line_range is
        omitted rather than guessed in regex-fallback mode).
        """
        for node in nodes:
            source_file = node.get("source_file")
            if not source_file:
                continue

            path = self._corpus_root / source_file
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue

            line_range = node.get("line_range")
            if isinstance(line_range, list) and len(line_range) == 2 and line_range != [0, 0]:
                begin, end = line_range
                sliced = "\n".join(text.splitlines()[begin - 1 : end])
                node["source_code"] = sliced if sliced else text
            else:
                node["source_code"] = text

        return nodes
