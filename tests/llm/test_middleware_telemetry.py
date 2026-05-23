import pytest
from codeograph.llm.middleware.telemetry_llm_provider import TelemetryLlmProvider
from codeograph.llm.types import CallContext, Purpose

def test_telemetry_middleware_emits_record(mock_llm_provider, tmp_telemetry_jsonl):
    ctx = CallContext(Purpose.ANNOTATE, "test_prompt", "v1", "hash", "corpus")
    provider = TelemetryLlmProvider(mock_llm_provider, tmp_telemetry_jsonl, ctx)
    # TODO(learner): Trigger a call, then read tmp_telemetry_jsonl file and assert record fields
    pass