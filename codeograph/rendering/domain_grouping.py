"""DomainGrouping ABC and concrete strategies (ADR-009 Fork 2).

A *domain group* is a logical module slice of the target codebase — e.g.
``"orders"``, ``"inventory"``, ``"auth"``.  The grouping strategy decides how
Java package names map to those slices.

Two strategies ship in v1:

``PackagePrefixGrouping`` (default)
    Strips the longest common prefix shared by all classes in the graph, then
    uses the *next* dot-separated segment as the group name.

    Example: given classes in ``com.example.orders.*`` and
    ``com.example.inventory.*``, the common prefix is ``com.example``, so
    groups become ``"orders"`` and ``"inventory"``.

``ManualMappingGrouping`` (opt-in via ``TypeScriptConfig.domain_mapping``)
    Reads an explicit ``{package_prefix: group_name}`` dict supplied by the
    user.  Packages not matching any prefix fall into the ``"misc"`` group.

Both strategies implement ``group(fqcn) -> str``, which is called once per
class name.  ``ClassSelector`` calls ``group()`` to bucket classes before
applying the stratified selection ladder (ADR-009).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["DomainGrouping", "ManualMappingGrouping", "PackagePrefixGrouping"]


class DomainGrouping(ABC):
    """Abstract strategy: maps a fully-qualified class name to a group label.

    Concrete strategies are constructed once per render call and reused for
    every class in the graph.
    """

    @abstractmethod
    def group(self, fqcn: str) -> str:
        """Return the domain-group label for *fqcn*.

        Args:
            fqcn: Fully-qualified Java class name,
                  e.g. ``"com.example.orders.OrderService"``.

        Returns:
            A short, filesystem-safe label such as ``"orders"``.
            Must never be empty.  The caller (``ClassSelector``) uses this
            label as a dict key and later as a NestJS module directory name.
        """

    @abstractmethod
    def prepare(self, all_fqcns: list[str]) -> None:
        """Pre-compute any state that requires seeing all class names at once.

        Called by ``ClassSelector`` before the first ``group()`` call.
        ``PackagePrefixGrouping`` uses this to derive the common prefix;
        ``ManualMappingGrouping`` is a no-op.

        Args:
            all_fqcns: Every fully-qualified class name present in the graph.
        """


# ---------------------------------------------------------------------------
# Strategy 1 — PackagePrefixGrouping
# ---------------------------------------------------------------------------


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

        packages = [_package_of(fqcn) for fqcn in all_fqcns]
        self._prefix = _longest_common_prefix(packages)

    def group(self, fqcn: str) -> str:
        pkg = _package_of(fqcn)
        suffix = pkg[len(self._prefix) :].lstrip(".")
        # Take the first segment after the stripped prefix.
        segment = suffix.split(".")[0] if suffix else ""
        return segment or "misc"


# ---------------------------------------------------------------------------
# Strategy 2 — ManualMappingGrouping
# ---------------------------------------------------------------------------


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
        pkg = _package_of(fqcn)
        for prefix, label in self._sorted_entries:
            if pkg == prefix or pkg.startswith(prefix + "."):
                return label
        return "misc"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _package_of(fqcn: str) -> str:
    """Return the package portion of *fqcn* (everything before the last dot)."""
    dot = fqcn.rfind(".")
    return fqcn[:dot] if dot != -1 else ""


def _longest_common_prefix(packages: list[str]) -> str:
    """Return the longest dot-aligned prefix shared by all *packages*.

    ``["com.example.orders", "com.example.inventory"]`` → ``"com.example"``
    ``["com.example"]`` → ``""``  (single element — no siblings to align with)
    ``[]`` → ``""``
    """
    if not packages:
        return ""

    # Split on "." and find common leading segments.
    split = [p.split(".") for p in packages]
    min_len = min(len(s) for s in split)

    common: list[str] = []
    for i in range(min_len):
        segment = split[0][i]
        if all(s[i] == segment for s in split):
            common.append(segment)
        else:
            break

    # A single class: the entire package becomes "common" but there are no
    # siblings, so strip one level to avoid a trivially-matching prefix that
    # swallows the group segment.
    if len(packages) == 1 and common:
        common = common[:-1]

    return ".".join(common)
