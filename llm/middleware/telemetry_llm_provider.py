import time
import uuid
from datetime import datetime, timezone
from typing import TypeVar
from codeograph.llm.provider import LlmProvider
from codeograph.llm.types import Tier, Message, LlmResult, CallContext
from codeograph.telemetry.base import TelemetryEmitter
from codeograph.telemetry.telemetry_record import TelemetryRecord
from codeograph.llm.errors import LlmError

T = TypeVar("T")

class TelemetryLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, emitter: TelemetryEmitter, ctx: CallContext):
        self._inner = inner
        self._emitter = emitter
        self._ctx = ctx

    def count_tokens(self, messages: list[Message]) -> int:
        return self._inner.count_tokens(messages)

    def complete_structured(
        self, tier: Tier, messages: list[Message], schema: type[T],
        *, override_model: str | None = None, max_tokens: int = 4096,
    ) -> LlmResult[T]:
        
        start_ts = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        
        try:
            res = self._inner.complete_structured(
                tier, messages, schema, 
                override_model=override_model, max_tokens=max_tokens
            )
            
            latency = int((time.monotonic() - start) * 1000)
            
            record = TelemetryRecord(
                ts=start_ts,
                trace_id=str(uuid.uuid4()),
                pipeline_name="UNKNOWN", 
                pipeline_run_id="UNKNOWN",
                corpus_id=self._ctx.corpus_id,
                provider="unknown",
                model=res.model,
                override_model=override_model,
                tier=tier.value,
                purpose=self._ctx.purpose.value,
                prompt_id=self._ctx.prompt_id,
                prompt_version=self._ctx.prompt_version,
                prompt_content_hash=self._ctx.prompt_content_hash,
                input_hash="TBD",
                output_hash="TBD",
                input_tokens=res.usage.input_tokens,
                output_tokens=res.usage.output_tokens,
                cached_tokens=res.usage.cached_tokens,
                input_estimated=res.usage.input_estimated,
                cache_hit=(latency == 0), 
                status="success",
                error_class=None,
                error_message=None,
                total_latency_ms=latency,
                attempts=[],
                cost_usd_est=0.0
            )
            self._emitter.emit(record)
            return res
            
        except LlmError as e:
            latency = int((time.monotonic() - start) * 1000)
            record = TelemetryRecord(
                ts=start_ts,
                trace_id=str(uuid.uuid4()),
                pipeline_name="UNKNOWN",
                pipeline_run_id="UNKNOWN",
                corpus_id=self._ctx.corpus_id,
                provider="unknown",
                model=override_model or tier.value,
                override_model=override_model,
                tier=tier.value,
                purpose=self._ctx.purpose.value,
                prompt_id=self._ctx.prompt_id,
                prompt_version=self._ctx.prompt_version,
                prompt_content_hash=self._ctx.prompt_content_hash,
                input_hash="TBD",
                output_hash=None,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                input_estimated=0,
                cache_hit=False,
                status="error",
                error_class=e.__class__.__name__,
                error_message=str(e),
                total_latency_ms=latency,
                attempts=[],
                cost_usd_est=0.0
            )
            self._emitter.emit(record)
            raise e
