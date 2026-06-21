from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class BooleanThreshold(BaseModel):
    kind: Literal["boolean"] = "boolean"
    expected: bool


class MinRatioThreshold(BaseModel):
    kind: Literal["min_ratio"] = "min_ratio"
    pass_at_or_above: float
    fail_below: float | None = None


class MaxCountThreshold(BaseModel):
    kind: Literal["max_count"] = "max_count"
    pass_at_or_below: int
    fail_above: int | None = None


class ScoreBandThreshold(BaseModel):
    kind: Literal["score_band"] = "score_band"
    pass_at_or_above: float | None
    fail_below: float | None


Threshold = Annotated[
    BooleanThreshold | MinRatioThreshold | MaxCountThreshold | ScoreBandThreshold,
    Field(discriminator="kind"),
]


class CheckResult(BaseModel):
    id: str
    category: Literal["graph", "code"]
    result: Literal["pass", "fail", "skip"] = "skip"
    value: bool | float | int | None
    threshold: Threshold
    rationale: str
    model_version: str | None = None
    prompt_id: str | None = None
    prompt_content_hash: str | None = None
    duration_ms: int
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def derive_result(self) -> CheckResult:
        v = self.value
        t = self.threshold

        # If value is missing, it's inherently a skip.
        # If details already specify a skip reason like preflight_missing_tool or deferred_v1.1,
        # we honour it and remain a skip regardless of value (which should be None anyway).
        if v is None or (self.result == "skip" and self.details.get("skip_reason") not in (None, "band_gap")):
            self.result = "skip"
            return self

        if isinstance(t, BooleanThreshold):
            self.result = "pass" if v == t.expected else "fail"
        elif isinstance(t, MinRatioThreshold):
            if v >= t.pass_at_or_above:
                self.result = "pass"
            elif t.fail_below is not None and v < t.fail_below:
                self.result = "fail"
            elif t.fail_below is None and v < t.pass_at_or_above:
                self.result = "fail"
            else:
                self.result = "skip"
                self.details["skip_reason"] = "band_gap"
        elif isinstance(t, MaxCountThreshold):
            if v <= t.pass_at_or_below:
                self.result = "pass"
            elif t.fail_above is not None and v > t.fail_above:
                self.result = "fail"
            elif t.fail_above is None and v > t.pass_at_or_below:
                self.result = "fail"
            else:
                self.result = "skip"
                self.details["skip_reason"] = "band_gap"
        elif isinstance(t, ScoreBandThreshold):
            if t.pass_at_or_above is not None and v >= t.pass_at_or_above:
                self.result = "pass"
            elif t.fail_below is not None and v < t.fail_below:
                self.result = "fail"
            else:
                self.result = "skip"
                self.details["skip_reason"] = "band_gap"

        return self


class ReproducibilityInfo(BaseModel):
    codeograph_version: str
    seed: int


class Scorecard(BaseModel):
    schema_version: str
    kind: Literal["graph", "ts", "go"]
    corpus_id: str
    run_timestamp: str
    run_id: str
    reproducibility: ReproducibilityInfo
    checks: list[CheckResult]


__all__ = [
    "BooleanThreshold",
    "MinRatioThreshold",
    "MaxCountThreshold",
    "ScoreBandThreshold",
    "Threshold",
    "CheckResult",
    "ReproducibilityInfo",
    "Scorecard",
]
