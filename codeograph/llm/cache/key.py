import hashlib
import json

from pydantic import BaseModel


def compute_input_hash(rendered_input: str) -> str:
    """SHA-256 of the rendered prompt input (all message bodies joined)."""
    return hashlib.sha256(rendered_input.encode("utf-8")).hexdigest()


def compute_schema_hash(schema: type[BaseModel]) -> str:
    """SHA-256 of the response schema's JSON Schema (sorted keys)."""
    return hashlib.sha256(json.dumps(schema.model_json_schema(), sort_keys=True).encode("utf-8")).hexdigest()


def compute_output_hash(output_body: str) -> str:
    """SHA-256 of the serialised LLM response body."""
    return hashlib.sha256(output_body.encode("utf-8")).hexdigest()


def compute_cache_key(
    *,
    provider: str,
    model: str,
    prompt_id: str,
    prompt_version: str,
    prompt_content_hash: str,
    rendered_input: str,
    schema: type[BaseModel],
    max_tokens: int,
) -> str:
    """Return a deterministic 16-hex-char cache key.

    The key composition includes every field that affects the response,
    and nothing that doesn't. See ADR-015 Fork 4 for the full rationale.
    """
    components = [
        provider,
        model,
        prompt_id,
        prompt_version,
        prompt_content_hash,
        compute_input_hash(rendered_input),
        compute_schema_hash(schema),
        str(max_tokens),
    ]
    joined = "\0".join(components)  # null byte — cannot appear in any component
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
