"""Logging formatters per ADR-022 Fork 4.

Two formatters drive the dual-emission logging substrate:

* :class:`PlaintextFormatter` — human-readable single-line output for the
  console. Format: ``%(asctime)s %(levelname)-5s [%(area)s] %(message)s``
  with ``datefmt="%Y-%m-%dT%H:%M:%SZ"`` UTC timestamps.
* :class:`JsonlFormatter` — one JSON object per line for ``<out>/logs.jsonl``,
  matching the locked per-record schema
  ``{ts, level, run_id, logger, context, msg}``.

The :class:`AreaFromContext` filter (in ``codeograph.logging_filters``)
populates ``record.area`` from ``extra["context"]["area"]`` so the
plaintext format string can render it. The filter is a no-op for the
JSONL formatter; the JSONL emitter reads ``extra["context"]`` directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any


class PlaintextFormatter(logging.Formatter):
    """Single-line plaintext formatter for the console handler.

    Uses the locked format string ``%(asctime)s %(levelname)-5s [%(area)s]
    %(message)s`` and ``datefmt="%Y-%m-%dT%H:%M:%SZ"``. The ``[%(area)s]``
    token is populated by the :class:`AreaFromContext` filter (configured
    on the handler that uses this formatter) so a logger that did not
    supply an ``area`` in its ``extra`` falls back to the last dot-
    separated segment of the logger name.
    """


class JsonlFormatter(logging.Formatter):
    """One-JSON-object-per-line formatter for ``<out>/logs.jsonl``.

    Per ADR-022 Fork 4, every record carries exactly these fields:

    * ``ts`` — ISO 8601 UTC with millisecond precision
    * ``level`` — DEBUG | INFO | WARNING | ERROR | CRITICAL
    * ``run_id`` — from the wrapping :class:`RunIdLoggerAdapter` (may be
      ``None`` when no run has been started, e.g. the ``cache stats``
      subcommand invoked before ``codeograph run``)
    * ``logger`` — full logger name (e.g. ``codeograph.evals.runner``)
    * ``context`` — dict of extra fields the logger passed in (includes
      ``area`` plus any component-specific keys like ``check_id``)
    * ``msg`` — the rendered log message

    Unknown fields on the LogRecord (added by Python's logging internals)
    are intentionally NOT emitted; the contract is exactly the six
    fields above so external tooling can rely on the schema.
    """

    # Use a default converter to UTC so the timestamp is timezone-
    # independent of the host's local time. formatTime(self, record, datefmt)
    # below handles ms precision explicitly.
    converter = __import__("time").gmtime

    def format(self, record: logging.LogRecord) -> str:
        # ISO 8601 with millisecond precision in UTC.
        ts = self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S")
        # formatTime returns the formatted string; append .SSS + Z.
        # record.msecs is set by logging's Formatter.formatTime when not None.
        ms = int(getattr(record, "msecs", 0))
        ts_with_ms = f"{ts}.{ms:03d}Z"

        # Extra fields the logger supplied; default to empty dict.
        context: dict[str, Any] = {}
        if hasattr(record, "context") and isinstance(record.context, dict):
            context = dict(record.context)

        # run_id comes from the wrapping RunIdLoggerAdapter. If no adapter
        # is in use (e.g. logger.getLogger() direct call), default to None.
        run_id = getattr(record, "run_id", None)

        payload = {
            "ts": ts_with_ms,
            "level": record.levelname,
            "run_id": run_id,
            "logger": record.name,
            "context": context,
            "msg": record.getMessage(),
        }
        # Single-line JSON; no indent; ensure_ascii=False so non-ASCII
        # paths and identifiers in `msg` survive round-trip cleanly.
        return json.dumps(payload, ensure_ascii=False)


__all__ = ["JsonlFormatter", "PlaintextFormatter"]
