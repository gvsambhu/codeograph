"""
TelemetrySessionManager — manages lifecycle, files, folders, and resources for telemetry/caching.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codeograph.config.settings import Settings
from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
from codeograph.telemetry.emitter import JsonlEmitter


@dataclass(frozen=True)
class TelemetrySession:
    """Holds active session telemetry resources."""
    cache_backend: SQLiteCacheBackend
    emitter: JsonlEmitter
    emitter_path: Path


class TelemetrySessionManager:
    """Manages setup and lifecycle of telemetry cache and log paths."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def start_session(self, corpus_id: str) -> TelemetrySession:
        # TODO: The learner should port the telemetry directory setup and resource initialization here.
        # This includes:
        # 1. Ensuring settings.cache_dir exists.
        # 2. Instantiating SQLiteCacheBackend at cache_dir / "cache.db".
        # 3. Setting up a unique run log filename via timestamp.
        # 4. Instantiating and returning the TelemetrySession with SQLiteCacheBackend and JsonlEmitter.
        raise NotImplementedError("TelemetrySessionManager.start_session needs to be implemented by the learner.")
