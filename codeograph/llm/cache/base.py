from abc import ABC, abstractmethod

from codeograph.llm.cache.cache_entry import CacheEntry
from codeograph.llm.cache.cache_stats import CacheStats


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> CacheEntry | None: ...
    @abstractmethod
    def put(self, key: str, entry: CacheEntry) -> None: ...
    @abstractmethod
    def stats(self) -> CacheStats: ...
    @abstractmethod
    def purge(
        self, *, older_than_days: int | None = None, prompt_version: str | None = None, model: str | None = None
    ) -> int: ...
