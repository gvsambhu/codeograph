"""Regression coverage for langchain_base._classify_error.

Before this test existed, the classifier's anthropic-vs-openai parity had zero
coverage — a 2026-07-06 manual run (MR-03) found that openai-style rate limit
errors (raised by every non-Anthropic provider via ChatOpenAI, ADR-013 D-013-7)
fell through to the generic LlmError branch instead of LlmTransientError, so
they were never retried by RetryingLlmProvider.
"""

import anthropic
import httpx
import openai
import pytest

from codeograph.llm.errors import (
    LlmAuthError,
    LlmBadInputError,
    LlmContentPolicyError,
    LlmError,
    LlmTransientError,
)
from codeograph.llm.providers.langchain_base import _classify_error


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://example.com")
    return httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})


@pytest.mark.parametrize(
    ("anthropic_exc", "openai_exc", "status", "expected_type"),
    [
        (anthropic.RateLimitError, openai.RateLimitError, 429, LlmTransientError),
        (anthropic.InternalServerError, openai.InternalServerError, 500, LlmTransientError),
        (anthropic.BadRequestError, openai.BadRequestError, 400, LlmBadInputError),
        (anthropic.AuthenticationError, openai.AuthenticationError, 401, LlmAuthError),
        (anthropic.PermissionDeniedError, openai.PermissionDeniedError, 403, LlmContentPolicyError),
    ],
)
def test_anthropic_and_openai_classify_identically(anthropic_exc, openai_exc, status, expected_type):
    resp = _response(status)
    a_err = anthropic_exc("boom", response=resp, body=None)
    o_err = openai_exc("boom", response=resp, body=None)

    a_classified = _classify_error(a_err)
    o_classified = _classify_error(o_err)

    assert isinstance(a_classified, expected_type)
    assert isinstance(o_classified, expected_type)


def test_openai_api_connection_error_is_transient():
    request = httpx.Request("POST", "https://example.com")
    err = openai.APIConnectionError(message="connection failed", request=request)

    assert isinstance(_classify_error(err), LlmTransientError)


def test_unrecognized_exception_is_unclassified_llm_error():
    classified = _classify_error(ValueError("not an LLM SDK error"))

    assert type(classified) is LlmError
    assert not isinstance(classified, LlmTransientError)
