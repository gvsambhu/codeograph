import json

from codeograph.telemetry.attempt import Attempt
from codeograph.telemetry.telemetry_record import TelemetryRecord


def test_jsonl_emitter_writes_lines(tmp_telemetry_jsonl, tmp_path):
    attempt = Attempt(
        attempt=1,
        latency_ms=450,
        status="success",
        error_class=None,
    )

    record = TelemetryRecord(
        run_id="run-123",
        ts="2025-01-01T12:00:00Z",
        trace_id="test_trace_123",
        pipeline_name="pass_1",
        pipeline_run_id="run_123",
        corpus_id="corpus_456",
        provider="anthropic",
        model="claude-3-5-sonnet",
        override_model=None,
        tier="FAST",
        purpose="ANNOTATE",
        prompt_id="prompt_123",
        prompt_version="v1",
        prompt_content_hash="prompt_hash_abc",
        input_hash="input_hash_abc",
        output_hash="output_hash_xyz",
        input_tokens=100,
        output_tokens=200,
        cached_tokens=0,
        input_estimated=None,
        cache_hit=False,
        status="success",
        error_class=None,
        error_message=None,
        total_latency_ms=1234,
        attempts=[attempt],
        cost_usd_est=0.0123,
    )

    tmp_telemetry_jsonl.emit(record)

    jsonl_path = tmp_path / "telemetry" / "test_telemetry.jsonl"
    with open(jsonl_path, encoding="utf-8") as f:
        line = f.readline()

    assert line.strip() != ""

    parsed = json.loads(line)

    assert parsed["trace_id"] == "test_trace_123"
    assert parsed["pipeline_name"] == "pass_1"
    assert parsed["provider"] == "anthropic"
    assert parsed["model"] == "claude-3-5-sonnet"
    assert parsed["prompt_version"] == "v1"
    assert parsed["status"] == "success"
    assert parsed["input_tokens"] == 100
    assert parsed["output_tokens"] == 200
    assert parsed["cached_tokens"] == 0
    assert parsed["cache_hit"] is False
    assert parsed["schema_version"] == "1.1"

    assert isinstance(parsed["attempts"], list)
    assert len(parsed["attempts"]) == 1
    assert isinstance(parsed["attempts"][0], dict)
    assert parsed["attempts"][0]["attempt"] == 1
    assert parsed["attempts"][0]["latency_ms"] == 450
    assert parsed["attempts"][0]["status"] == "success"
    assert parsed["attempts"][0]["error_class"] is None
