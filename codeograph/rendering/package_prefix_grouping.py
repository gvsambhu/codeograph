"""Strategy 1 — PackagePrefixGrouping."""

from __future__ import annotations

from codeograph.rendering.base import DomainGrouping, longest_common_prefix, package_of

__all__ = ["PackagePrefixGrouping"]


class PackagePrefixGrouping(DomainGrouping):
    """Strip the longest common package prefix; use the next segment as group.

    If all FQCNs share the prefix ``com.example``, then:
        ``com.example.orders.OrderService`` → ``"orders"``
        ``com.example.inventory.Item``      → ``"inventory"``

    Edge cases:
    - A single class whose package has no siblings falls into ``"misc"``.
    - Classes that live *at* the common-prefix level (no further segment)
      fall into ``"misc"``.
    - An empty graph produces no groups.

    **Known limitation — mixed-vendor codebases:**
    Auto-detection is reliable only when all classes share a deep common
    prefix (single-vendor codebases, e.g. everything under ``com.example``).
    For mixed-vendor graphs (e.g. ``com.example.orders.*`` alongside
    ``com.other.Lib``), the LCP collapses to a shallow ancestor (``"com"``),
    stripping too little and causing all domains to merge into one group.
    When the CLI detects that auto-grouping produced only one group from a
    large class set it emits a warning and suggests switching to
    ``ManualMappingGrouping`` via the ``[render.typescript.domain_mapping]``
    config key.  See ADR-009 Amendments.
    """

    def __init__(self) -> None:
        self._prefix: str = ""

    def prepare(self, all_fqcns: list[str]) -> None:
        """Derive the common package prefix from all FQCNs."""
        if not all_fqcns:
            self._prefix = ""
            return

        packages = [package_of(fqcn) for fqcn in all_fqcns]
        self._prefix = longest_common_prefix(packages)

    def group(self, fqcn: str) -> str:
        pkg = package_of(fqcn)
        suffix = pkg[len(self._prefix) :].lstrip(".")
        # Take the first segment after the stripped prefix.
        segment = suffix.split(".")[0] if suffix else ""
        return segment or "misc"
