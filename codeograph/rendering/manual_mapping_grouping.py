"""Strategy 2 — ManualMappingGrouping."""

from __future__ import annotations

from codeograph.rendering.base import DomainGrouping, package_of

__all__ = ["ManualMappingGrouping"]


class ManualMappingGrouping(DomainGrouping):
    """Explicit ``{package_prefix: group_name}`` mapping supplied by the user.

    The longest matching prefix wins (most-specific-first).  Classes not
    matched by any prefix fall into ``"misc"``.

    Args:
        mapping: Dict of Java package prefix → group label.
                 Keys should be dot-separated package prefixes, e.g.
                 ``{"com.example.orders": "orders",
                    "com.example.auth": "auth"}``.
    """

    def __init__(self, mapping: dict[str, str]) -> None:
        # Sort by descending key length so longest-prefix wins in group().
        self._sorted_entries: list[tuple[str, str]] = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)

    def prepare(self, all_fqcns: list[str]) -> None:  # noqa: ARG002
        """No-op — mapping is fully specified at construction time."""

    def group(self, fqcn: str) -> str:
        pkg = package_of(fqcn)
        for prefix, label in self._sorted_entries:
            if pkg == prefix or pkg.startswith(prefix + "."):
                return label
        return "misc"
