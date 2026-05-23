from dataclasses import dataclass

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_s: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_s: float = 30.0
    respect_retry_after_header: bool = True
