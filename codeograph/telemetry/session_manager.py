"""
TelemetrySessionManager — manages lifecycle, files, folders, and resources for telemetry/caching.
"""

from __future__ import annotations

import datetime

from codeograph.config.settings import Settings
from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend
from codeograph.telemetry.emitter import JsonlEmitter
from codeograph.telemetry.session import TelemetrySession


class TelemetrySessionManager:
    """Manages setup and lifecycle of telemetry cache and log paths."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def start_session(self, corpus_id: str, run_id: str) -> TelemetrySession:
        self._settings.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_backend = SQLiteCacheBackend(self._settings.cache_dir / "cache.db")
        telemetry_dir = self._settings.cache_dir / "telemetry"
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        emitter_path = telemetry_dir / f"run-{run_id}.jsonl"
        emitter = JsonlEmitter(emitter_path)

        return TelemetrySession(
            cache_backend=cache_backend,
            emitter=emitter,
            emitter_path=emitter_path,
        )
