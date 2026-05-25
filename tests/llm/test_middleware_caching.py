import json

from pydantic import BaseModel

from codeograph.llm.cache.cache_entry import CacheEntry
from codeograph.llm.cache.key import compute_cache_key
from codeograph.llm.middleware.caching_llm_provider import CachingLlmProvider
from codeograph.llm.types import CallContext, LlmResult, Message, Purpose, Tier, TokenUsage


class DummySchema(BaseModel):
    text: str


def test_caching_middleware_hit(mock_llm_provider, tmp_cache_db):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")
    caching_provider = CachingLlmProvider(mock_llm_provider, tmp_cache_db, ctx)

    messages = [Message(role="user", content="Hello")]
    max_tokens = 4096
    rendered_input = "\n".join(m.content for m in messages)

    key = compute_cache_key(
        model=Tier.FAST.value,
        prompt_id=ctx.prompt_id,
        prompt_version=ctx.prompt_version,
        prompt_content_hash=ctx.prompt_content_hash,
        rendered_input=rendered_input,
        schema=DummySchema,
        max_tokens=max_tokens,
    )

    cached_entry = CacheEntry(
        cache_key=key,
        provider="unknown",
        model="claude-3-5-sonnet",
        tier=Tier.FAST.value,
        purpose=ctx.purpose.value,
        prompt_id=ctx.prompt_id,
        prompt_version=ctx.prompt_version,
        prompt_content_hash=ctx.prompt_content_hash,
        input_hash="TBD",
        schema_hash="TBD",
        max_tokens=max_tokens,
        input_body=rendered_input,
        output_body='{"text":"cached hello"}',
        token_usage_json=json.dumps(
            {
                "input_tokens": 10,
                "output_tokens": 20,
                "cached_tokens": 0,
                "input_estimated": None,
            }
        ),
        created_at="2026-05-24T10:00:00+00:00",
        hit_count=0,
        last_hit_at=None,
    )
    tmp_cache_db.put(key, cached_entry)

    result = caching_provider.complete_structured(
        Tier.FAST,
        messages,
        DummySchema,
        max_tokens=max_tokens,
    )

    assert result.value == DummySchema(text="cached hello")
    assert result.usage == TokenUsage(10, 20, 0, None)
    assert result.model == "claude-3-5-sonnet"
    assert result.latency_ms == 0
    assert len(mock_llm_provider.calls) == 0


def test_caching_middleware_miss(mock_llm_provider, tmp_cache_db):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")
    caching_provider = CachingLlmProvider(mock_llm_provider, tmp_cache_db, ctx)

    messages = [Message(role="user", content="Hello")]
    max_tokens = 4096

    mock_result = LlmResult(
        value=DummySchema(text="fresh hello"),
        usage=TokenUsage(11, 22, 0, None),
        model="mock-model",
        latency_ms=123,
    )
    mock_llm_provider.mock_response = mock_result

    result = caching_provider.complete_structured(
        Tier.FAST,
        messages,
        DummySchema,
        max_tokens=max_tokens,
    )

    assert result == mock_result
    assert len(mock_llm_provider.calls) == 1

    rendered_input = "\n".join(m.content for m in messages)
    key = compute_cache_key(
        model=Tier.FAST.value,
        prompt_id=ctx.prompt_id,
        prompt_version=ctx.prompt_version,
        prompt_content_hash=ctx.prompt_content_hash,
        rendered_input=rendered_input,
        schema=DummySchema,
        max_tokens=max_tokens,
    )

    cached = tmp_cache_db.get(key)
    assert cached is not None
    assert cached.model == "mock-model"
    assert cached.tier == Tier.FAST.value
    assert cached.purpose == Purpose.ANNOTATE.value
    assert cached.input_body == rendered_input
    assert json.loads(cached.output_body) == {"text": "fresh hello"}
    assert json.loads(cached.token_usage_json) == {
        "input_tokens": 11,
        "output_tokens": 22,
        "cached_tokens": 0,
        "input_estimated": None,
    }
