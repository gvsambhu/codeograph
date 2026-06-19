"""
TelemetrySession — holds active session telemetry resources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
from codeograph.telemetry.emitter import JsonlEmitter


@dataclass(frozen=True)
class TelemetrySession:
    """Holds active session telemetry resources."""

    cache_backend: SQLiteCacheBackend
    emitter: JsonlEmitter
    emitter_path: Path
