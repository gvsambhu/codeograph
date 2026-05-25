"""CLI commands for managing the LLM cache."""

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import click

from codeograph.config.settings import Settings
from codeograph.llm.cache.sqlite_backend import SQLiteCacheBackend


@click.group(name="cache")
def cache_cli() -> None:
    """Manage the local Codeograph LLM cache."""
    pass


@cache_cli.command()
def stats() -> None:
    """Show cache size, entry count, and pass-specific breakdown."""
    settings = Settings()
    db_path = settings.cache_dir / "cache.db"
    if not db_path.exists():
        click.echo("Cache is empty or does not exist.")
        return

    backend = SQLiteCacheBackend(db_path)
    stats = backend.stats()

    # TODO(learner): format output to match preferences
    click.echo(f"Cache stats for {db_path}:")
    click.echo(f"Total entries: {stats.total_entries}")
    click.echo(f"Total size: {stats.total_size_bytes} bytes")


@cache_cli.command()
@click.option("--all", "purge_all", is_flag=True, help="Purge all entries.")
@click.option("--older-than", metavar="DAYS", type=int, help="Purge entries older than N days.")
@click.option("--prompt-version", metavar="VERSION", help="Purge entries for a specific prompt version (e.g., v2).")
@click.option("--model", metavar="MODEL", help="Purge entries for a specific model.")
@click.option("--force", is_flag=True, help="Actually perform the deletion. By default, this is a dry run.")
def purge(purge_all: bool, older_than: int | None, prompt_version: str | None, model: str | None, force: bool) -> None:
    """Purge entries from the cache (dry-run by default unless --force is provided)."""
    settings = Settings()
    db_path = settings.cache_dir / "cache.db"
    if not db_path.exists():
        click.echo("Cache is empty or does not exist.")
        return

    backend = SQLiteCacheBackend(db_path)

    if not any([purge_all, older_than, prompt_version, model]):
        click.echo("Must specify at least one purge criteria (--all, --older-than, --prompt-version, --model).")
        return

    if not force:
        click.echo("[DRY RUN] Would purge cache entries matching criteria.")
        click.echo("Run again with --force to actually delete.")
        return

    # If purge_all is true, we delete everything. The backend.purge doesn't have an `all` param
    # but we can just pass no filters or execute a raw delete.
    if purge_all:
        deleted = backend.purge()
    else:
        deleted = backend.purge(older_than_days=older_than, prompt_version=prompt_version, model=model)

    click.echo(f"Purged {deleted} entries.")


@cache_cli.command()
@click.option("--since", metavar="DAYS", type=int, default=30, help="Analyze runs from the last N days (default: 30).")
def report(since: int) -> None:
    """Aggregate cross-run cache performance from telemetry JSONL files."""
    settings = Settings()
    telemetry_dir = settings.cache_dir / "telemetry"
    if not telemetry_dir.exists():
        click.echo("No telemetry data found.")
        return

    cutoff = datetime.now(UTC) - timedelta(days=since)

    files = sorted(telemetry_dir.glob("*.jsonl"))
    if not files:
        click.echo("No telemetry data found.")
        return

    total_runs = len(files)
    total_calls = 0
    cache_hits = 0
    cost_saved = 0.0
    cost_incurred = 0.0

    weekly: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "hits": 0})
    hit_prompts: Counter[str] = Counter()
    miss_prompts: Counter[str] = Counter()

    def parse_ts(value: str) -> datetime:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt

    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_raw = rec.get("ts")
                if not ts_raw:
                    continue
                try:
                    ts = parse_ts(ts_raw)
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

    hit_rate = (cache_hits / total_calls * 100.0) if total_calls else 0.0

    click.echo(f"Cache performance over last {since} days:")
    click.echo(f"  Total runs: {total_runs}")
    click.echo(f"  Total calls: {total_calls:,}")
    click.echo(f"  Cache hits: {cache_hits:,} ({hit_rate:.1f}%)")
    click.echo(f"  Cost saved: ~${cost_saved:.2f}")
    click.echo(f"  Cost incurred: ~${cost_incurred:.2f}")
    click.echo("")

    click.echo("Hit rate trend (weekly):")
    for week_start in sorted(weekly.keys()):
        calls = weekly[week_start]["calls"]
        hits = weekly[week_start]["hits"]
        rate = (hits / calls * 100.0) if calls else 0.0
        click.echo(f"  Week of {week_start}: {rate:.0f}%")
    click.echo("")

    click.echo("Top 5 most-hit prompts:")
    for prompt, count in hit_prompts.most_common(5):
        click.echo(f"  {prompt} — {count:,} hits")
    if not hit_prompts:
        click.echo("  (none)")
    click.echo("")

    click.echo("Top 5 most-missed prompts:")
    for prompt, count in miss_prompts.most_common(5):
        click.echo(f"  {prompt} — {count:,} misses")
    if not miss_prompts:
        click.echo("  (none)")
