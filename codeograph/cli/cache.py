"""CLI commands for managing the LLM cache."""

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
    from codeograph.telemetry.telemetry_report_aggregator import TelemetryReportAggregator

    settings = Settings()
    telemetry_dir = settings.cache_dir / "telemetry"
    if not telemetry_dir.exists() or not any(telemetry_dir.glob("*.jsonl")):
        click.echo("No telemetry data found.")
        return

    rpt = TelemetryReportAggregator().aggregate(telemetry_dir, since_days=since)

    click.echo(f"Cache performance over last {since} days:")
    click.echo(f"  Total runs: {rpt.total_runs}")
    click.echo(f"  Total calls: {rpt.total_calls:,}")
    click.echo(f"  Cache hits: {rpt.cache_hits:,} ({rpt.hit_rate:.1f}%)")
    click.echo(f"  Cost saved: ~${rpt.cost_saved:.2f}")
    click.echo(f"  Cost incurred: ~${rpt.cost_incurred:.2f}")
    click.echo("")

    click.echo("Hit rate trend (weekly):")
    for week_start in sorted(rpt.weekly.keys()):
        calls = rpt.weekly[week_start]["calls"]
        hits = rpt.weekly[week_start]["hits"]
        rate = (hits / calls * 100.0) if calls else 0.0
        click.echo(f"  Week of {week_start}: {rate:.0f}%")
    click.echo("")

    click.echo("Top 5 most-hit prompts:")
    for prompt, count in rpt.hit_prompts.most_common(5):
        click.echo(f"  {prompt} — {count:,} hits")
    if not rpt.hit_prompts:
        click.echo("  (none)")
    click.echo("")

    click.echo("Top 5 most-missed prompts:")
    for prompt, count in rpt.miss_prompts.most_common(5):
        click.echo(f"  {prompt} — {count:,} misses")
    if not rpt.miss_prompts:
        click.echo("  (none)")
