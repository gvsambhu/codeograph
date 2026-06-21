import time
import uuid
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel

from codeograph.llm.cache.key import compute_input_hash, compute_output_hash
from codeograph.llm.errors import LlmError
from codeograph.llm.models import CallContext, LlmResult, Message, Tier
from codeograph.llm.provider import LlmProvider
from codeograph.telemetry.base import TelemetryEmitter
from codeograph.telemetry.telemetry_record import TelemetryRecord

T = TypeVar("T", bound=BaseModel)


class TelemetryLlmProvider(LlmProvider):
    def __init__(self, inner: LlmProvider, emitter: TelemetryEmitter, ctx: CallContext):
        self._inner = inner
        self._emitter = emitter
        self._ctx = ctx

    def resolve_model(self, tier: Tier, override_model: str | None = None) -> str:
        return self._inner.resolve_model(tier, override_model)

    def count_tokens(self, messages: list[Message]) -> int:
        return self._inner.count_tokens(messages)

    def complete_structured(
        self,
        tier: Tier,
        messages: list[Message],
        schema: type[T],
        *,
        override_model: str | None = None,
        max_tokens: int = 4096,
    ) -> LlmResult[T]:

        rendered_input = "\n".join(m.content for m in messages)
        input_hash = compute_input_hash(rendered_input)
        start_ts = datetime.now(UTC).isoformat()
        start = time.monotonic()

        try:
            res = self._inner.complete_structured(
                tier, messages, schema, override_model=override_model, max_tokens=max_tokens
            )

            latency = int((time.monotonic() - start) * 1000)
            output_body = res.value.model_dump_json()

            record = TelemetryRecord(
                run_id=self._ctx.run_id,
                ts=start_ts,
                trace_id=str(uuid.uuid4()),
                pipeline_name=self._ctx.pipeline_name,
                pipeline_run_id=self._ctx.pipeline_run_id,
                corpus_id=self._ctx.corpus_id,
                provider=self._ctx.provider_name,
                model=res.model,
                override_model=override_model,
                tier=tier.value,
                purpose=self._ctx.purpose.value,
                prompt_id=self._ctx.prompt_id,
                prompt_version=self._ctx.prompt_version,
                prompt_content_hash=self._ctx.prompt_content_hash,
                input_hash=input_hash,
                output_hash=compute_output_hash(output_body),
                input_tokens=res.usage.input_tokens,
                output_tokens=res.usage.output_tokens,
                cached_tokens=res.usage.cached_tokens,
                input_estimated=res.usage.input_estimated,
                cache_hit=res.cache_hit,
                status="success",
                error_class=None,
                error_message=None,
                total_latency_ms=latency,
                attempts=[],
                cost_usd_est=0.0,
            )
            self._emitter.emit(record)
            return res

        except LlmError as e:
            latency = int((time.monotonic() - start) * 1000)
            record = TelemetryRecord(
                run_id=self._ctx.run_id,
                ts=start_ts,
                trace_id=str(uuid.uuid4()),
                pipeline_name=self._ctx.pipeline_name,
                pipeline_run_id=self._ctx.pipeline_run_id,
                corpus_id=self._ctx.corpus_id,
                provider=self._ctx.provider_name,
                model=override_model or tier.value,
                override_model=override_model,
                tier=tier.value,
                purpose=self._ctx.purpose.value,
                prompt_id=self._ctx.prompt_id,
                prompt_version=self._ctx.prompt_version,
                prompt_content_hash=self._ctx.prompt_content_hash,
                input_hash=input_hash,
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
                cost_usd_est=0.0,
            )
            self._emitter.emit(record)
            raise e
