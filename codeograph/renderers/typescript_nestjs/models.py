"""Models for TypeScript/NestJS renderer."""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["RenderedSource"]


class RenderedSource(BaseModel):
    """Single-field wrapper used with ``complete_structured()`` for code-gen output.

    The render prompt instructs the model to return its TypeScript source code
    in the ``content`` field.  Using ``complete_structured()`` keeps the
    provider abstraction intact — no raw-text completion method is needed.
    The model must JSON-escape the TypeScript content; Pydantic validates it.
    """

    content: str
