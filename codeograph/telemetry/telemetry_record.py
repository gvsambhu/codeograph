from dataclasses import dataclass

from codeograph.telemetry.attempt import Attempt


@dataclass(frozen=True)
class TelemetryRecord:
    ts: str  # ISO 8601 UTC
    trace_id: str
    pipeline_name: str  # pass_1 | pass_2 | pass_3
    pipeline_run_id: str
    corpus_id: str
    provider: str
    model: str
    override_model: str | None
    tier: str  # FAST | DEEP | RENDER
    purpose: str  # ANNOTATE | SYNTHESIZE | RENDER
    prompt_id: str
    prompt_version: str
    prompt_content_hash: str
    input_hash: str
    output_hash: str | None  # null on terminal failure
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    input_estimated: int | None
    cache_hit: bool
    status: str  # success | error
    error_class: str | None
    error_message: str | None  # short summary, NOT stack trace
    total_latency_ms: int
    attempts: list[Attempt]
    cost_usd_est: float
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = self.__dict__.copy()
        d["attempts"] = [a.__dict__ for a in self.attempts]
        return d
