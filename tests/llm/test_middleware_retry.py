import pytest
from codeograph.llm.middleware.retrying_llm_provider import RetryingLlmProvider
from codeograph.llm.middleware.retry_policy import RetryPolicy

def test_retry_middleware_success_first_try(mock_llm_provider):
    policy = RetryPolicy(max_attempts=3)
    provider = RetryingLlmProvider(mock_llm_provider, policy)
    # TODO(learner): Assert inner provider called once
    pass

def test_retry_middleware_transient_error(mock_llm_provider):
    policy = RetryPolicy(max_attempts=3)
    provider = RetryingLlmProvider(mock_llm_provider, policy)
    # TODO(learner): Setup mock to fail with LlmTransientError, then succeed, assert attempts
    pass