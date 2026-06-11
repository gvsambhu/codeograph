"""Run-id generation per ADR-022 Fork 3.

Format: ``YYYY-MM-DDTHH-MM-SSZ-<6 hex>`` — chronologically sortable
(sort-lexicographic == sort-chronological), collision-resistant over a
same-second window (24 random bits), cross-OS filesystem-safe (no
``:``/``.``/``_``), and stdlib-only (``datetime`` + ``secrets``).

Generation moment: at pipeline start, in ``codeograph run``'s orchestrator
(M7). Recorded on the first manifest write; never regenerated mid-run.
``codeograph eval`` reads the existing manifest's ``run_id`` and does NOT
generate a new one.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

# Public regex; importable as codeograph.manifest.run_id.RUN_ID_PATTERN.
# Mirrors the format produced by generate_run_id() below; kept as a module
# constant so tests, manifest readers, and external validators can share it.
RUN_ID_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[0-9a-f]{6}$"

# Pre-compiled form for repeated use (regex.match on a non-compiled
# pattern caches internally, but we expose a compiled object for callers
# that need a Pattern object directly).
_RUN_ID_RE = re.compile(RUN_ID_PATTERN)


def generate_run_id() -> str:
    """Generate a run id in the locked format.

    Example: ``2026-05-30T14-32-11Z-a3f2c8``.

    Returns a fresh value on every call. The 6-hex suffix is 24 random
    bits from ``secrets.token_hex``; collision risk over a same-second
    window is negligible for any realistic CI parallel-matrix size.
    """
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    suffix = secrets.token_hex(3)  # 6 hex chars = 24 random bits
    return f"{timestamp}-{suffix}"


__all__ = ["RUN_ID_PATTERN", "generate_run_id"]
