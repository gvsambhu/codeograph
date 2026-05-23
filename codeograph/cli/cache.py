"""CLI commands for managing the LLM cache."""

from pathlib import Path
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

    click.echo(f"Aggregating telemetry since {since} days ago...")
    # TODO(learner): Implement cross-run JSONL aggregation logic per ADR-015
    click.echo("Report formatting left as TODO for learner.")
