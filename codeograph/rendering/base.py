"""DomainGrouping ABC (ADR-009 Fork 2)."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["DomainGrouping", "package_of", "longest_common_prefix"]


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


def package_of(fqcn: str) -> str:
    """Return the package portion of *fqcn* (everything before the last dot)."""
    dot = fqcn.rfind(".")
    return fqcn[:dot] if dot != -1 else ""


def longest_common_prefix(packages: list[str]) -> str:
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
