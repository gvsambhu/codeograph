"""Confirmation tests for the D-015-1 cache-key composition contract (ADR-015 Fork 4).

D-015-1 states that ``provider`` is the first discriminating component of the
8-component cache key.  These tests pin that contract at the unit level so a
future refactor cannot silently drop ``provider`` from the key without a
test failure.
"""

from __future__ import annotations

from pydantic import BaseModel

from codeograph.llm.cache.key import compute_cache_key


class DummySchema(BaseModel):
    text: str


class OtherSchema(BaseModel):
    count: int


def _key(
    *,
    provider: str = "anthropic",
    model: str = "claude-3-5-sonnet-20241022",
    prompt_id: str = "annotate_class",
    prompt_version: str = "v1",
    prompt_content_hash: str = "aabbcc",
    rendered_input: str = "Describe this class.",
    schema: type[BaseModel] = DummySchema,
    max_tokens: int = 2048,
) -> str:
    return compute_cache_key(
        provider=provider,
        model=model,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        prompt_content_hash=prompt_content_hash,
        rendered_input=rendered_input,
        schema=schema,
        max_tokens=max_tokens,
    )


def test_key_format_is_16_hex_chars() -> None:
    """compute_cache_key always returns a 16-character lowercase hex string."""
    key = _key()
    assert len(key) == 16
    assert key == key.lower()
    assert all(c in "0123456789abcdef" for c in key)


def test_key_is_deterministic() -> None:
    """Same inputs always produce the same key (no time/random component)."""
    assert _key() == _key()


def test_provider_is_discriminating_component() -> None:
    """D-015-1: changing only provider changes the key.

    This is the cross-cluster contract: an 'anthropic' run and an 'openai' run
    with identical prompts and models must never collide in the cache.
    """
    key_anthropic = _key(provider="anthropic")
    key_openai = _key(provider="openai")
    key_bedrock = _key(provider="bedrock/us-east-1")

    assert key_anthropic != key_openai
    assert key_anthropic != key_bedrock
    assert key_openai != key_bedrock


def test_model_is_discriminating_component() -> None:
    """Changing only model changes the key."""
    assert _key(model="claude-3-5-sonnet-20241022") != _key(model="claude-3-haiku-20240307")


def test_prompt_id_is_discriminating_component() -> None:
    """Changing only prompt_id changes the key."""
    assert _key(prompt_id="annotate_class") != _key(prompt_id="synthesize_domain")


def test_prompt_version_is_discriminating_component() -> None:
    """Changing only prompt_version changes the key."""
    assert _key(prompt_version="v1") != _key(prompt_version="v2")


def test_prompt_content_hash_is_discriminating_component() -> None:
    """Changing only prompt_content_hash changes the key."""
    assert _key(prompt_content_hash="aabbcc") != _key(prompt_content_hash="ddeeff")


def test_rendered_input_is_discriminating_component() -> None:
    """Changing only rendered_input changes the key."""
    assert _key(rendered_input="Describe this class.") != _key(rendered_input="A completely different prompt body.")


def test_schema_is_discriminating_component() -> None:
    """Changing only schema changes the key."""
    assert _key(schema=DummySchema) != _key(schema=OtherSchema)


def test_max_tokens_is_discriminating_component() -> None:
    """Changing only max_tokens changes the key."""
    assert _key(max_tokens=2048) != _key(max_tokens=4096)
