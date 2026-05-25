from dataclasses import replace

from codeograph.llm.cache.cache_entry import CacheEntry


def test_sqlite_cache_put_get(tmp_cache_db):
    entry = CacheEntry(
        cache_key="test_key",
        provider="anthropic",
        model="claude-3-5-sonnet",
        tier="default",
        purpose="unit_test",
        prompt_id="prompt_123",
        prompt_version="v1",
        prompt_content_hash="prompt_hash_abc",
        input_hash="input_hash_abc",
        schema_hash="schema_hash_abc",
        max_tokens=4096,
        input_body='{"messages":[{"role":"user","content":"Hello"}]}',
        output_body='{"content":[{"type":"text","text":"Hi there"}]}',
        token_usage_json='{"input_tokens":10,"output_tokens":20,"total_tokens":30}',
        created_at="2026-05-24T14:00:00Z",
        hit_count=0,
        last_hit_at=None,
    )

    # Arrange + act: write and read once
    tmp_cache_db.put("test_key", entry)
    fetched = tmp_cache_db.get("test_key")

    # First get() returns the stored row *before* increment
    assert fetched is not None
    assert fetched == entry
    assert fetched.hit_count == 0

    # Second get() should now see the incremented hit_count
    fetched_again = tmp_cache_db.get("test_key")
    assert fetched_again is not None
    assert fetched_again.hit_count == 1

    # Optional: unknown key returns None
    assert tmp_cache_db.get("unknown_key") is None


def test_sqlite_cache_stats(tmp_cache_db):
    initial_stats = tmp_cache_db.stats()

    assert initial_stats.total_entries == 0
    assert initial_stats.total_size_bytes > 0

    entry1 = CacheEntry(
        cache_key="test_key_1",
        provider="anthropic",
        model="claude-3-5-sonnet",
        tier="default",
        purpose="unit_test",
        prompt_id="prompt_123",
        prompt_version="v1",
        prompt_content_hash="prompt_hash_abc",
        input_hash="input_hash_abc",
        schema_hash="schema_hash_abc",
        max_tokens=4096,
        input_body='{"messages":[{"role":"user","content":"Hello"}]}',
        output_body='{"content":[{"type":"text","text":"Hi there"}]}',
        token_usage_json='{"input_tokens":10,"output_tokens":20,"total_tokens":30}',
        created_at="2026-05-24T14:00:00Z",
        hit_count=0,
        last_hit_at=None,
    )
    entry2 = replace(entry1, cache_key="test_key_2")

    tmp_cache_db.put("test_key_1", entry1)
    tmp_cache_db.put("test_key_2", entry2)

    updated_stats = tmp_cache_db.stats()

    assert updated_stats.total_entries == 2
    assert updated_stats.total_size_bytes > 0
    assert updated_stats.total_size_bytes >= initial_stats.total_size_bytes


def test_sqlite_cache_purge(tmp_cache_db):
    base_entry = CacheEntry(
        cache_key="test_key_1",
        provider="anthropic",
        model="claude-3-5-sonnet",
        tier="default",
        purpose="unit_test",
        prompt_id="prompt_123",
        prompt_version="v1",
        prompt_content_hash="prompt_hash_abc",
        input_hash="input_hash_abc",
        schema_hash="schema_hash_abc",
        max_tokens=4096,
        input_body='{"messages":[{"role":"user","content":"Hello"}]}',
        output_body='{"content":[{"type":"text","text":"Hi there"}]}',
        token_usage_json='{"input_tokens":10,"output_tokens":20,"total_tokens":30}',
        created_at="2026-05-24T14:00:00Z",
        hit_count=0,
        last_hit_at=None,
    )

    entry1 = base_entry
    entry2 = replace(
        base_entry,
        cache_key="test_key_2",
        prompt_version="v2",
    )
    entry3 = replace(
        base_entry,
        cache_key="test_key_3",
        prompt_version="v2",
        model="gpt-4o",
    )

    tmp_cache_db.put("test_key_1", entry1)
    tmp_cache_db.put("test_key_2", entry2)
    tmp_cache_db.put("test_key_3", entry3)

    deleted_count = tmp_cache_db.purge(prompt_version="v1")
    assert deleted_count == 1
    assert tmp_cache_db.stats().total_entries == 2

    # Optional extra coverage: purge the remaining gpt-4o row
    deleted_count = tmp_cache_db.purge(model="gpt-4o")
    assert deleted_count == 1
    assert tmp_cache_db.stats().total_entries == 1
