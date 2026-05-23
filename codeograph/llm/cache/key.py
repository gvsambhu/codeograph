import hashlib
import json
from pydantic import BaseModel

def compute_cache_key(
    *,
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
        model,
        prompt_id,
        prompt_version,
        prompt_content_hash,
        hashlib.sha256(rendered_input.encode("utf-8")).hexdigest(),
        hashlib.sha256(
            json.dumps(schema.model_json_schema(), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        str(max_tokens),
    ]
    joined = "\0".join(components)     # null byte — cannot appear in any component
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
