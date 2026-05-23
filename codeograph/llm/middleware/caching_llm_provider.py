import json
from datetime import datetime, timezone
from typing import TypeVar
from codeograph.llm.provider import LlmProvider
from codeograph.llm.types import Tier, Message, LlmResult, TokenUsage, CallContext
from codeograph.llm.cache.base import CacheBackend
from codeograph.llm.cache.cache_entry import CacheEntry
from codeograph.llm.cache.key import compute_cache_key

T = TypeVar("T")

class CachingLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, cache: CacheBackend, ctx: CallContext):
        self._inner = inner
        self._cache = cache
        self._ctx = ctx

    def count_tokens(self, messages: list[Message]) -> int:
        return self._inner.count_tokens(messages)

    def complete_structured(
        self, tier: Tier, messages: list[Message], schema: type[T],
        *, override_model: str | None = None, max_tokens: int = 4096,
    ) -> LlmResult[T]:
        model_name = override_model or tier.value
        rendered_input = "\\n".join(m.content for m in messages)
        
        key = compute_cache_key(
            model=model_name,
            prompt_id=self._ctx.prompt_id,
            prompt_version=self._ctx.prompt_version,
            prompt_content_hash=self._ctx.prompt_content_hash,
            rendered_input=rendered_input,
            schema=schema,
            max_tokens=max_tokens
        )
        
        cached = self._cache.get(key)
        if cached:
            val = schema(**json.loads(cached.output_body))
            usage = TokenUsage(**json.loads(cached.token_usage_json))
            return LlmResult(
                value=val,
                usage=usage,
                model=cached.model,
                latency_ms=0
            )
            
        res = self._inner.complete_structured(
            tier, messages, schema, 
            override_model=override_model, max_tokens=max_tokens
        )
        
        entry = CacheEntry(
            cache_key=key,
            provider="unknown",
            model=res.model,
            tier=tier.value,
            purpose=self._ctx.purpose.value,
            prompt_id=self._ctx.prompt_id,
            prompt_version=self._ctx.prompt_version,
            prompt_content_hash=self._ctx.prompt_content_hash,
            input_hash="TBD", 
            schema_hash="TBD",
            max_tokens=max_tokens,
            input_body=rendered_input,
            output_body=res.value.model_dump_json() if hasattr(res.value, 'model_dump_json') else "{}",
            token_usage_json=json.dumps(res.usage.__dict__),
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self._cache.put(key, entry)
        
        return res
