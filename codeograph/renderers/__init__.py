"""Pluggable renderer package (ADR-008).

Public surface:
    Renderer         — generic ABC every target-language renderer implements
    CompileCheck     — frozen dataclass describing one compile/typecheck command
    RendererRegistry — decorator-based registry + factory (registry.py)

Import order matters: concrete renderer packages (e.g. typescript_nestjs)
self-register via @RendererRegistry.register(...) at import time.  The CLI
imports them explicitly after importing this package so the registry is
populated before RendererRegistry.build() is called.
"""

from codeograph.renderers.base import CompileCheck, Renderer
from codeograph.renderers.registry import RendererRegistry

__all__ = ["CompileCheck", "Renderer", "RendererRegistry"]
