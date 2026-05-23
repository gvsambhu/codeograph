from dataclasses import dataclass

@dataclass(frozen=True)
class CacheEntry:
    cache_key: str
    provider: str
    model: str
    tier: str
    purpose: str
    prompt_id: str
    prompt_version: str
    prompt_content_hash: str
    input_hash: str
    schema_hash: str
    max_tokens: int
    input_body: str
    output_body: str
    token_usage_json: str
    created_at: str
    hit_count: int = 0
    last_hit_at: str | None = None
