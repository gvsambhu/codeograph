"""Data models for renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

__all__ = ["CompileCheck"]


@dataclass(frozen=True)
class CompileCheck:
    """Declarative description of one compile / typecheck command (ADR-008 Fork 3).

    The eval framework (DC4) iterates ``renderer.compile_checks()``,
    preflights ``required_tools`` via ``shutil.which``, runs each command
    with ``subprocess.run``, and records pass / skip / fail in the scorecard.

    Attributes:
        name:              Human-readable label shown in the scorecard row.
        cmd:               Command tuple passed to ``subprocess.run``.
        workdir:           Working directory relative to the rendered output root.
                           Defaults to the root itself.
        required_tools:    Tool names to preflight via ``shutil.which``.
                           A missing tool produces a recorded ``skip``, not a crash.
        pass_on_exit_codes: Exit codes that count as a pass.  Defaults to ``(0,)``.
    """

    name: str
    cmd: tuple[str, ...]
    workdir: PurePosixPath = field(default_factory=lambda: PurePosixPath("."))
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    pass_on_exit_codes: tuple[int, ...] = field(default_factory=lambda: (0,))
