"""Logging configuration per ADR-022 Fork 4.

Single Python ``logging.config.dictConfig`` sets up two handlers
attached to the ``codeograph`` logger tree:

* **console** — plaintext to ``sys.stderr``; default level INFO; filtered
  by :class:`AreaFromContext` so the ``[%(area)s]`` plaintext token
  renders. Console verbosity is overridable via ``configure_logging``.
* **file** — JSONL to ``<out>/logs.jsonl``; always at DEBUG (audit
  trail). Skipped when ``out_dir is None`` (e.g. ``codeograph cache
  stats`` invoked before any run).

:class:`RunIdLoggerAdapter` wraps a top-level logger so every record
emitted via the adapter carries the same ``run_id``. The JSONL schema
locks ``run_id`` as one of the six top-level fields per ADR-022 Fork 4.
"""

from __future__ import annotations

import logging
import logging.config
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# LoggerAdapter — propagates run_id into every record
# ---------------------------------------------------------------------------


class RunIdLoggerAdapter(logging.LoggerAdapter[logging.Logger]):
    """LoggerAdapter that injects ``run_id`` into every record.

    Usage::

        log = RunIdLoggerAdapter(logging.getLogger(__name__), run_id)
        log.info("started", extra={"context": {"area": "orchestrator"}})

    The adapter is the load-bearing mechanism that keeps
    ``JsonlFormatter``'s ``run_id`` field populated without forcing
    every log call to thread the value through ``extra=`` manually.
    ``run_id`` may be ``None`` (e.g. ``cache stats`` before any run);
    the JSONL emitter then serializes it as ``null`` per the schema.
    """

    def __init__(self, logger: logging.Logger, run_id: str | None) -> None:
        super().__init__(logger, {"run_id": run_id})

    def process(
        self,
        msg: Any,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[Any, MutableMapping[str, Any]]:
        # Merge any caller-supplied extra with our own run_id slot. The
        # caller's extra wins for non-run_id keys (so log.info(extra=
        # {"context": {...}}) still works), but run_id is always set by
        # the adapter and cannot be overridden per-call.
        extra = dict(kwargs.get("extra") or {})
        extra["run_id"] = self.extra.get("run_id")  # type: ignore[union-attr]
        kwargs["extra"] = extra
        return msg, kwargs


# ---------------------------------------------------------------------------
# Configuration bootstrap
# ---------------------------------------------------------------------------


def _build_logging_config(out_dir: Path | None, console_level: str) -> dict[str, Any]:
    """Build the ``dictConfig`` payload.

    The file handler's ``filename`` is set dynamically; when ``out_dir``
    is ``None`` (e.g. ``codeograph cache stats`` invoked before any
    ``codeograph run``), the file handler is omitted entirely so the
    audit trail doesn't get a stale or zero-length ``logs.jsonl`` in
    the current working directory.
    """
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "jsonl": {
                "()": "codeograph.logging_formatters.JsonlFormatter",
            },
            "plaintext": {
                "()": "codeograph.logging_formatters.PlaintextFormatter",
                "format": "%(asctime)s %(levelname)-5s [%(area)s] %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%SZ",
            },
        },
        "filters": {
            "area_from_context": {
                "()": "codeograph.logging_filters.AreaFromContext",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "plaintext",
                "level": console_level,
                "filters": ["area_from_context"],
            },
        },
        "loggers": {
            "codeograph": {
                # Logger level is DEBUG; handlers filter further. Setting
                # logger to DEBUG lets the file handler capture everything
                # regardless of console verbosity.
                "level": "DEBUG",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        config["handlers"]["file"] = {
            "class": "logging.FileHandler",
            "filename": str(out_dir / "logs.jsonl"),
            "formatter": "jsonl",
            "level": "DEBUG",
            "encoding": "utf-8",
        }
        # Attach the file handler to the codeograph logger alongside
        # the console handler.
        config["loggers"]["codeograph"]["handlers"] = ["file", "console"]

    return config


def configure_logging(console_level: str = "INFO", out_dir: Path | None = None) -> None:
    """Bootstrap the codeograph logging substrate.

    Idempotent: calling twice (e.g. once at CLI startup, again at the
    orchestrator's first log line) replaces the previous configuration
    cleanly without leaking handlers. The same ``LOGGING_CONFIG`` is
    reconstructed from scratch each call.

    :param console_level: one of ``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
        ``"ERROR"``, ``"CRITICAL"``. CLI flags (``-v``/``-q``/``--log-level``)
        normalise to this value before invocation. File handler ignores
        this — file always captures at DEBUG.
    :param out_dir: directory to write ``logs.jsonl`` into. ``None``
        skips the file handler (used by subcommands that run before any
        ``codeograph run``, e.g. ``cache stats``, ``cache purge``).
    """
    config = _build_logging_config(out_dir=out_dir, console_level=console_level)
    logging.config.dictConfig(config)


__all__ = [
    "LOGGING_CONFIG",
    "RunIdLoggerAdapter",
    "configure_logging",
]


# Backwards-compatible module-level constant for callers that prefer
# to inspect the default config (e.g. tests). Built from the same
# builder so the shape stays in lockstep with configure_logging().
LOGGING_CONFIG: dict[str, Any] = _build_logging_config(
    out_dir=None,
    console_level="INFO",
)
