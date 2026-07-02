"""Cross-run telemetry aggregation for the ``codeograph cache report`` command (SRP-03)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass
class TelemetryReport:
    """Aggregated cross-run cache performance metrics."""

    total_runs: int
    total_calls: int
    cache_hits: int
    cost_saved: float
    cost_incurred: float
    weekly: dict[str, dict[str, int]] = field(default_factory=dict)
    hit_prompts: Counter[str] = field(default_factory=Counter)
    miss_prompts: Counter[str] = field(default_factory=Counter)

    @property
    def hit_rate(self) -> float:
        return (self.cache_hits / self.total_calls * 100.0) if self.total_calls else 0.0


class TelemetryReportAggregator:
    """Aggregates cross-run cache metrics from all JSONL files in a telemetry directory.

    Complements :class:`~codeograph.telemetry.stats_aggregator.TelemetryStatsAggregator`
    which operates on a single emitter file for per-pass stats.  This class
    works across the whole directory for the multi-run ``cache report`` view.
    """

    def aggregate(self, telemetry_dir: Path, *, since_days: int) -> TelemetryReport:
        """Read all JSONL files in *telemetry_dir* and return aggregated metrics.

        Only records whose ``ts`` field falls within the last *since_days* days
        are included.
        """
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        files = sorted(telemetry_dir.glob("*.jsonl"))

        total_runs = len(files)
        total_calls = 0
        cache_hits = 0
        cost_saved = 0.0
        cost_incurred = 0.0
        weekly: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "hits": 0})
        hit_prompts: Counter[str] = Counter()
        miss_prompts: Counter[str] = Counter()

        for path in files:
            with open(path, encoding="utf-8") as fh:
                for raw_line in fh:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        rec = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    ts_raw = rec.get("ts")
                    if not ts_raw:
                        continue
                    try:
                        ts = _parse_ts(ts_raw)
                    except ValueError:
                        continue

                    if ts < cutoff:
                        continue

                    total_calls += 1
                    prompt_key = f"{rec.get('prompt_id', 'unknown')} {rec.get('prompt_version', 'unknown')}"
                    hit = bool(rec.get("cache_hit", False))
                    est_cost = float(rec.get("cost_usd_est", 0.0) or 0.0)
                    week_start = (ts - timedelta(days=ts.weekday())).date().isoformat()
                    weekly[week_start]["calls"] += 1

                    if hit:
                        cache_hits += 1
                        cost_saved += est_cost
                        weekly[week_start]["hits"] += 1
                        hit_prompts[prompt_key] += 1
                    else:
                        cost_incurred += est_cost
                        miss_prompts[prompt_key] += 1

        return TelemetryReport(
            total_runs=total_runs,
            total_calls=total_calls,
            cache_hits=cache_hits,
            cost_saved=cost_saved,
            cost_incurred=cost_incurred,
            weekly=dict(weekly),
            hit_prompts=hit_prompts,
            miss_prompts=miss_prompts,
        )


def _parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
