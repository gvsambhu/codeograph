from dataclasses import dataclass

@dataclass(frozen=True)
class PromptMetadata:
    id: str
    version: str
    purpose: str
    required_vars: list[str]
    optional_vars: list[str]
    cacheable_segments: list[str]
    content_hash_pin: str

@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    metadata: PromptMetadata
    system: str
    user: str
    content_hash: str
