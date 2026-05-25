from dataclasses import dataclass


@dataclass(frozen=True)
class Attempt:
    attempt: int
    latency_ms: int
    status: str
    error_class: str | None
