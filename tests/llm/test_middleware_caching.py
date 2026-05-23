import pytest
from codeograph.llm.middleware.caching_llm_provider import CachingLlmProvider
from codeograph.llm.types import CallContext, Purpose

def test_caching_middleware_hit(mock_llm_provider, tmp_cache_db):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")
    caching_provider = CachingLlmProvider(mock_llm_provider, tmp_cache_db, ctx)
    # TODO(learner): Setup a cache hit scenario and assert inner provider wasn't called
    pass

def test_caching_middleware_miss(mock_llm_provider, tmp_cache_db):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")
    caching_provider = CachingLlmProvider(mock_llm_provider, tmp_cache_db, ctx)
    # TODO(learner): Setup a cache miss scenario, assert inner provider called, and cache was written
    pass