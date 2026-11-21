"""Raised by a renderer when a spend ceiling ends the run part-way."""

from __future__ import annotations

from pathlib import PurePosixPath

from codeograph.llm.errors import LlmCeilingExceededError

__all__ = ["RenderStoppedError"]


class RenderStoppedError(LlmCeilingExceededError):
    """A spend ceiling stopped rendering; the files rendered before it are kept.

    Attributes:
        file_map: The files produced before the ceiling was reached, for the caller to write.
        rendered: How many classes were rendered.
        total:    How many classes were selected for rendering.
    """

    def __init__(
        self,
        ceiling: LlmCeilingExceededError,
        file_map: dict[PurePosixPath, bytes],
        rendered: int,
        total: int,
    ) -> None:
        super().__init__(f"{ceiling}; rendered {rendered} of {total} classes")
        self.file_map = file_map
        self.rendered = rendered
        self.total = total
