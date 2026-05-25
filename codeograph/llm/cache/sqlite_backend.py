import sqlite3
import threading
from pathlib import Path

from codeograph.llm.cache.base import CacheBackend
from codeograph.llm.cache.cache_entry import CacheEntry
from codeograph.llm.cache.cache_stats import CacheStats


class SQLiteCacheBackend(CacheBackend):
    def __init__(self, path: Path):
        self._path = path
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            if version < 1:
                self._conn.executescript("""
                    CREATE TABLE cache_entries (
                      cache_key TEXT PRIMARY KEY,
                      provider TEXT NOT NULL,
                      model TEXT NOT NULL,
                      tier TEXT NOT NULL,
                      purpose TEXT NOT NULL,
                      prompt_id TEXT NOT NULL,
                      prompt_version TEXT NOT NULL,
                      prompt_content_hash TEXT NOT NULL,
                      input_hash TEXT NOT NULL,
                      schema_hash TEXT NOT NULL,
                      max_tokens INTEGER NOT NULL,
                      input_body TEXT NOT NULL,
                      output_body TEXT NOT NULL,
                      token_usage_json TEXT NOT NULL,
                      created_at TIMESTAMP NOT NULL,
                      hit_count INTEGER NOT NULL DEFAULT 0,
                      last_hit_at TIMESTAMP
                    );

                    CREATE INDEX idx_prompt ON cache_entries(prompt_id, prompt_version);
                    CREATE INDEX idx_model  ON cache_entries(model);
                    CREATE INDEX idx_created ON cache_entries(created_at);
                    
                    PRAGMA user_version = 1;
                """)
                self._conn.commit()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM cache_entries WHERE cache_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE cache_entries "
                    "SET hit_count = hit_count + 1, last_hit_at = datetime('now') "
                    "WHERE cache_key = ?",
                    (key,),
                )
                self._conn.commit()
                return CacheEntry(**dict(row))
            return None

    def put(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cache_entries (
                    cache_key, provider, model, tier, purpose, prompt_id, prompt_version,
                    prompt_content_hash, input_hash, schema_hash, max_tokens, input_body,
                    output_body, token_usage_json, created_at, hit_count, last_hit_at
                ) VALUES (
                    :cache_key, :provider, :model, :tier, :purpose, :prompt_id, :prompt_version,
                    :prompt_content_hash, :input_hash, :schema_hash, :max_tokens, :input_body,
                    :output_body, :token_usage_json, :created_at, :hit_count, :last_hit_at
                )
            """,
                entry.__dict__,
            )
            self._conn.commit()

    def stats(self) -> CacheStats:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM cache_entries")
            count = cursor.fetchone()[0]
            size = self._path.stat().st_size if self._path.exists() else 0
            return CacheStats(total_entries=count, total_size_bytes=size)

    def purge(
        self, *, older_than_days: int | None = None, prompt_version: str | None = None, model: str | None = None
    ) -> int:
        query = "DELETE FROM cache_entries WHERE 1=1"
        params = []
        if older_than_days is not None:
            query += " AND created_at < datetime('now', ?)"
            params.append(f"-{older_than_days} days")
        if prompt_version is not None:
            query += " AND prompt_version = ?"
            params.append(prompt_version)
        if model is not None:
            query += " AND model = ?"
            params.append(model)

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            deleted = cursor.rowcount
            self._conn.commit()
            return deleted
