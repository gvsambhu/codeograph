from dataclasses import dataclass


@dataclass(frozen=True)
class CacheStats:
    total_entries: int
    total_size_bytes: int
