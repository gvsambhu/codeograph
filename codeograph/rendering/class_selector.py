"""ClassSelector — budget-aware class selection for rendering (ADR-009).

ADR-009 defines a three-tier strategy ladder applied *per domain group*:

Tier 1 — take_all
    ``n ≤ cap``  → include every class in the group as-is.

Tier 2 — top_n_v1
    ``cap < n < 2·cap``  → sort by descending WMC (nulls last), take the top
    ``cap`` entries.  Simple heuristic — no bucketing needed.

Tier 3 — stratified_threshold_v1
    ``n ≥ 2·cap``  → bucket into three tiers, fill the cap proportionally:

        OR-high  : ``CBO ≥ 5  OR  WMC ≥ 20``   (complex/highly-coupled)
        OR-low   : ``CBO ≤ 1  AND WMC ≤ 5``     (simple/isolated)
        mid      : everything else

    Fill order: round-robin high → mid → low per cycle so a small budget
    yields at least one class from each populated difficulty band.
    Thresholds cite Lanza & Marinescu (2006) *Object-Oriented Metrics in
    Practice*, pp 16-18, as required by ADR-004.

    Classes without metrics (``extraction_mode != "ast"``) are placed into
    the *mid* bucket so they are not unfairly promoted or demoted.

``SelectionResult`` is the frozen value object returned by ``select()``.  Its
8 base fields are described in ADR-009; the 3 ADR-010 Fork 9 extension fields
support the unsupported-feature policy machinery in the TypeScript renderer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codeograph.rendering.models import SelectionResult

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import (
        ClassNode,
        CodeographKnowledgeGraph,
        EnumNode,
        InterfaceNode,
        RecordNode,
    )
    from codeograph.rendering.base import DomainGrouping

    # ADR-010 locks TypeScript mapping targets for all four of these kinds
    # (classes, repository interfaces, record DTOs, enums) — WMC/CBO (ADR-004)
    # are class-only metrics, so callers must read them via getattr(), never
    # direct attribute access, to stay safe across this union.
    RenderableNode = ClassNode | InterfaceNode | RecordNode | EnumNode

__all__ = ["ClassSelector"]

# ---------------------------------------------------------------------------
# ADR-009 thresholds (Lanza & Marinescu 2006, pp 16-18)
# ---------------------------------------------------------------------------
_HIGH_CBO_THRESHOLD = 5  # CBO ≥ this → OR-high bucket
_HIGH_WMC_THRESHOLD = 20  # WMC ≥ this → OR-high bucket
_LOW_CBO_THRESHOLD = 1  # CBO ≤ this → candidate for OR-low
_LOW_WMC_THRESHOLD = 5  # WMC ≤ this → candidate for OR-low (AND with CBO)

# Default per-group budget cap (overridden by TypeScriptConfig.render_budget)
# FR-13: default = 3 (one per bucket at minimum cap) — DC3-02.
_DEFAULT_CAP = 3


# ---------------------------------------------------------------------------
# ClassSelector
# ---------------------------------------------------------------------------


class ClassSelector:
    """Apply ADR-009's three-tier selection ladder to a ``CodeographKnowledgeGraph``.

    Usage::

        grouping = PackagePrefixGrouping()
        selector = ClassSelector(cap=50, grouping=grouping)
        results = selector.select(graph)
        for result in results:
            print(result.group_name, result.strategy, len(result.selected))

    Args:
        cap:      Per-group budget cap (maximum classes to select per group).
        grouping: A prepared or un-prepared ``DomainGrouping`` strategy.
                  ``select()`` calls ``grouping.prepare()`` before grouping.
    """

    def __init__(
        self,
        cap: int = _DEFAULT_CAP,
        grouping: DomainGrouping | None = None,
    ) -> None:
        self._cap = cap
        if grouping is None:
            from codeograph.rendering.package_prefix_grouping import PackagePrefixGrouping

            self._grouping: DomainGrouping = PackagePrefixGrouping()
        else:
            self._grouping = grouping

    def select(self, graph: CodeographKnowledgeGraph) -> list[SelectionResult]:
        """Run the selection ladder over all domain groups in *graph*.

        Returns:
            One ``SelectionResult`` per domain group, in ascending group-name
            order.  Groups with zero classes are omitted.
        """
        class_nodes = self._extract_renderable_nodes(graph)
        if not class_nodes:
            return []

        all_fqcns = [n.id for n in class_nodes]
        self._grouping.prepare(all_fqcns)

        # Bucket by group
        groups: dict[str, list[RenderableNode]] = {}
        for node in class_nodes:
            label = self._grouping.group(node.id)
            groups.setdefault(label, []).append(node)

        results: list[SelectionResult] = []
        for group_name in sorted(groups):
            members = groups[group_name]
            results.append(self._apply_ladder(group_name, members))

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_renderable_nodes(self, graph: CodeographKnowledgeGraph) -> list[RenderableNode]:
        """Return the class/interface/record/enum entries from *graph* (ADR-010).

        Excludes AnnotationTypeNode (no locked TypeScript mapping target) and
        module/field/method nodes (never rendering targets in their own right).
        """
        from codeograph.graph.models.graph_schema import ClassNode as CN
        from codeograph.graph.models.graph_schema import EnumNode as EN
        from codeograph.graph.models.graph_schema import InterfaceNode as IN
        from codeograph.graph.models.graph_schema import RecordNode as RN

        out: list[RenderableNode] = []
        for node_wrapper in graph.nodes:
            node = node_wrapper.root
            if isinstance(node, (CN, IN, RN, EN)):
                out.append(node)
        return out

    def _apply_ladder(self, group_name: str, members: list[RenderableNode]) -> SelectionResult:
        """Select members from one group using the ADR-009 tier ladder."""
        n = len(members)
        cap = self._cap

        if n <= cap:
            return SelectionResult(
                selected=tuple(m.id for m in members),
                excluded=(),
                strategy="take_all",
                group_name=group_name,
                cap=cap,
                total_in_group=n,
                metrics_missing_count=_count_missing_metrics(members),
                high_count=0,
            )

        if n < 2 * cap:
            return self._top_n_v1(group_name, members, cap, n)

        return self._stratified_threshold_v1(group_name, members, cap, n)

    def _top_n_v1(self, group_name: str, members: list[RenderableNode], cap: int, total: int) -> SelectionResult:
        """Tier 2: sort descending by WMC, take top ``cap``."""
        sorted_members = sorted(members, key=lambda m: (_wmc_of(m) is None, -(_wmc_of(m) or 0)))
        selected = sorted_members[:cap]
        excluded = sorted_members[cap:]
        return SelectionResult(
            selected=tuple(m.id for m in selected),
            excluded=tuple(m.id for m in excluded),
            strategy="top_n_v1",
            group_name=group_name,
            cap=cap,
            total_in_group=total,
            metrics_missing_count=_count_missing_metrics(members),
            high_count=0,
        )

    def _stratified_threshold_v1(
        self, group_name: str, members: list[RenderableNode], cap: int, total: int
    ) -> SelectionResult:
        """Tier 3: bucket into high/mid/low, fill proportionally.

        Thresholds (Lanza & Marinescu 2006, pp 16-18):
            OR-high : CBO ≥ 5  OR  WMC ≥ 20
            OR-low  : CBO ≤ 1  AND WMC ≤ 5
            mid     : everything else (including metrics-missing classes)

        WMC/CBO (ADR-004) are ClassNode-only metrics; interfaces/records/enums
        (ADR-010) have neither field at all, so they fall into missing-metrics
        mid-bucket treatment the same way a class with unresolved metrics does.
        """
        high: list[RenderableNode] = []
        mid: list[RenderableNode] = []
        low: list[RenderableNode] = []
        missing_metrics = 0

        for m in members:
            cbo = _cbo_of(m)
            wmc = _wmc_of(m)
            if cbo is None or wmc is None:
                missing_metrics += 1
                mid.append(m)
                continue
            if cbo >= _HIGH_CBO_THRESHOLD or wmc >= _HIGH_WMC_THRESHOLD:
                high.append(m)
            elif cbo <= _LOW_CBO_THRESHOLD and wmc <= _LOW_WMC_THRESHOLD:
                low.append(m)
            else:
                mid.append(m)

        # Sort each bucket by descending WMC (nulls last).
        def _wmc_key(m: RenderableNode) -> tuple[bool, int]:
            return (_wmc_of(m) is None, -(_wmc_of(m) or 0))

        high.sort(key=_wmc_key)
        mid.sort(key=_wmc_key)
        low.sort(key=_wmc_key)

        # Round-robin fill: take one from each populated bucket per cycle
        # until cap is reached (D-009-1). Sequential fill (old: high → mid → low)
        # caused a small cap to select only high-complexity classes, defeating
        # the difficulty-spread that D-009-1 explicitly locked.
        nonempty = [b for b in (high, mid, low) if b]
        pointers = [0] * len(nonempty)
        selected: list[RenderableNode] = []
        while len(selected) < cap:
            added_this_cycle = 0
            for i, bucket in enumerate(nonempty):
                if len(selected) >= cap:
                    break
                if pointers[i] < len(bucket):
                    selected.append(bucket[pointers[i]])
                    pointers[i] += 1
                    added_this_cycle += 1
            if added_this_cycle == 0:
                break  # all buckets exhausted

        selected_ids = {m.id for m in selected}
        excluded = [m for m in members if m.id not in selected_ids]

        return SelectionResult(
            selected=tuple(m.id for m in selected),
            excluded=tuple(m.id for m in excluded),
            strategy="stratified_threshold_v1",
            group_name=group_name,
            cap=cap,
            total_in_group=total,
            metrics_missing_count=missing_metrics,
            high_count=len(high),
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _wmc_of(node: RenderableNode) -> int | None:
    """WMC (ADR-004) is ClassNode-only; other renderable kinds have no such field."""
    return getattr(node, "wmc", None)


def _cbo_of(node: RenderableNode) -> int | None:
    """CBO (ADR-004) is ClassNode-only; other renderable kinds have no such field."""
    return getattr(node, "cbo", None)


def _count_missing_metrics(members: list[RenderableNode]) -> int:
    return sum(1 for m in members if _cbo_of(m) is None or _wmc_of(m) is None)
