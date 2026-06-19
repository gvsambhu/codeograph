"""
TelemetryStatsAggregator — parses JSONL logs to compile run metrics and cache hit rates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codeograph.llm.types import Purpose
from codeograph.manifest.models import CacheStats


class TelemetryStatsAggregator:
    """Aggregates telemetry JSONL records into high-level pass cache statistics."""

    def aggregate(self, emitter_path: Path) -> dict[str, CacheStats] | None:
        purpose_to_pass = {
            Purpose.ANNOTATE.value: "pass_1",
            Purpose.SYNTHESIZE.value: "pass_2",
        }
        per_pass: dict[str, list[dict[str, Any]]] = {"pass_1": [], "pass_2": []}
        if emitter_path.exists():
            with open(emitter_path, encoding="utf-8") as tf:
                for line in tf:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    pass_label = purpose_to_pass.get(rec.get("purpose"))
                    if pass_label:
                        per_pass[pass_label].append(rec)

        aggregated: dict[str, CacheStats] = {}
        for pass_label, recs in per_pass.items():
            if not recs:
                continue
            calls = len(recs)
            hits = sum(1 for r in recs if r.get("cache_hit"))
            hit_rate = round((hits / calls) if calls else 0.0, 4)
            aggregated[pass_label] = CacheStats(
                calls=calls,
                hits=hits,
                hit_rate=hit_rate,
            )

        return aggregated if aggregated else None
