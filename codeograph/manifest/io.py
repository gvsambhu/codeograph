"""Manifest IO per ADR-022 Fork 7.

Two-phase write/read discipline:

* :func:`write` — strict on write. Pydantic's ``extra='forbid'`` rejects
  unknown fields and shape regressions at the boundary. Indent-2
  ``json`` for human readability; the manifest is not subject to the
  golden-graph byte-equal contract.
* :func:`read` — lenient on read. Unknown top-level fields (from a
  newer codeograph release writing a ``1.x.x`` manifest the current
  codeograph doesn't yet know about) are dropped with a DEBUG log
  record; the rest of the manifest validates against the current
  Pydantic schema. This is the forward-compat path within
  ``1.x.x`` per ADR-022 Fork 1's strict-additive rule.

The read path is implemented by *pre-filtering* the raw JSON dict to
the set of fields the current Pydantic model declares, rather than
relying on ``model_validate(strict=False)`` — the latter controls
*type* strictness (e.g. ``int`` vs ``bool``) and does NOT bypass
``extra='forbid'``. The ADR-022 §Fork 7 sketch's ``strict=False``
wording was loose; the dropped-unknown-fields-with-DEBUG-log
behaviour is the load-bearing requirement and is implemented
explicitly here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from codeograph.manifest.models import Manifest

logger = logging.getLogger(__name__)


def write(manifest: Manifest, path: Path) -> None:
    """Strict-on-write per ADR-022 Fork 7.

    Validates via Pydantic (the constructor's own ``extra='forbid'`` is
    the boundary check) and serialises with ``indent=2`` for human
    readability. The manifest is not subject to the golden-graph
    byte-equal contract; canonical-form rules from ADR-006 do not
    apply.

    Creates parent directories as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8", newline="")


def read(path: Path) -> Manifest:
    """Lenient-on-read per ADR-022 Fork 7.

    Forward-compatible across ``1.x.x`` versions: unknown top-level
    fields (introduced by a newer codeograph release that the current
    Pydantic schema doesn't know about) are dropped with a DEBUG log
    record naming the dropped key. The remaining fields validate
    against the current schema. This honours ADR-022 Fork 1's
    strict-additive rule: an old codeograph install reading a
    new-codeograph manifest succeeds silently for additive fields
    and surfaces any genuine contract violation as a ValidationError.

    The DEBUG log key is the dropped top-level field name; the value
    is truncated to 80 chars in the log to avoid dumping
    path/shape content.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        # Corrupt or wrong-shape manifest; let the strict validator
        # produce the canonical ValidationError.
        return Manifest.model_validate(raw)

    known_fields = set(Manifest.model_fields.keys())
    unknown_keys = [k for k in raw if k not in known_fields]
    if unknown_keys:
        for key in unknown_keys:
            value = raw[key]
            rendered = repr(value)
            if len(rendered) > 80:
                rendered = rendered[:77] + "..."
            logger.debug(
                "manifest read: dropped unknown top-level field %s=%s (forward-compat; "
                "current schema does not declare this field)",
                key,
                rendered,
            )
        filtered = {k: v for k, v in raw.items() if k in known_fields}
        return Manifest.model_validate(filtered)

    return Manifest.model_validate(raw)


__all__ = ["read", "write"]
