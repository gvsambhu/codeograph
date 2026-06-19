"""String manipulation and mapping helpers for TypeScript/NestJS rendering."""

from __future__ import annotations


def to_pascal_case(name: str) -> str:
    """``"orders"`` → ``"Orders"``, ``"order-items"`` → ``"OrderItems"``."""
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_"))


def to_kebab_case(name: str) -> str:
    """``"OrderService"`` → ``"order-service"``."""
    import re

    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s1)
    return s2.lower()


def stereotype_to_role_suffix(stereotype: object) -> str:
    """Return the NestJS file-role suffix for *stereotype*.

    The suffix is appended to the kebab-case class stem so that
    ``_render_domain_module`` can classify output files with a plain
    ``path.name.endswith(suffix)`` check (ADR-010 Fork 8).

    *stereotype* may be a ``Stereotype`` enum value or a plain string.
    The function coerces to string via ``.value`` (enum) or ``str()``.

    Mapping::

        RestController / Controller → .controller.ts
        Service                     → .service.ts
        Repository                  → .repository.ts
        Entity                      → .entity.ts
        ControllerAdvice            → .filter.ts
        anything else               → .ts   (DTOs, exceptions, config classes)
    """
    _MAP: dict[str, str] = {
        "RestController": ".controller.ts",
        "Controller": ".controller.ts",
        "Service": ".service.ts",
        "Repository": ".repository.ts",
        "Entity": ".entity.ts",
        "ControllerAdvice": ".filter.ts",
    }
    # ClassNode.stereotype is a Stereotype enum; extract its string value.
    key: str = getattr(stereotype, "value", None) or (str(stereotype) if stereotype else "")
    return _MAP.get(key, ".ts")
