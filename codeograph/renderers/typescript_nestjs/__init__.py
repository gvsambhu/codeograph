"""TypeScript/NestJS renderer package (ADR-008, ADR-010).

Self-registers with RendererRegistry at import time via
``@RendererRegistry.register("typescript")`` on TypeScriptRenderer.
"""

from codeograph.renderers.typescript_nestjs.typescript_renderer import TypeScriptRenderer

__all__ = ["TypeScriptRenderer"]
