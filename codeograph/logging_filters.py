"""Logging filters per ADR-022 Fork 4.

:class:`AreaFromContext` populates ``record.area`` so the
:class:`PlaintextFormatter` can render ``[%(area)s]`` in its format
string. The source of truth is ``extra["context"]["area"]`` (set by
loggers that wrap a context object); the fallback is the last dot-
separated segment of the logger name (e.g. ``codeograph.evals.runner``
→ ``runner``).

The filter is configured on the **console** handler only. The JSONL
handler reads ``extra["context"]`` directly via
:class:`codeograph.logging_formatters.JsonlFormatter`; populating
``record.area`` for JSONL is a no-op (the field is not in the locked
JSONL schema).
"""

from __future__ import annotations

import logging


class AreaFromContext(logging.Filter):
    """Populate ``record.area`` from ``extra["context"]["area"]``.

    Falls back to the last dot-separated segment of the logger name when
    no ``area`` is supplied (e.g. a bare ``logging.getLogger(__name__)``
    call without an adapter). The fallback ensures the
    ``[%(area)s]`` plaintext token never renders as ``[None]``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Always let the record through; this filter only enriches it.
        area: str | None = None

        # Prefer the explicit context.area set by the logger / adapter.
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            candidate = context.get("area")
            if isinstance(candidate, str) and candidate:
                area = candidate

        if area is None:
            # Fall back to the last logger-name segment.
            area = record.name.rsplit(".", 1)[-1] if record.name else "root"

        record.area = area
        return True


__all__ = ["AreaFromContext"]
