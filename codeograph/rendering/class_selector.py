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

    Fill order: high → mid → low, each tier sorted by descending WMC.
    Thresholds cite Lanza & Marinescu (2006) *Object-Oriented Metrics in
    Practice*, pp 16-18, as required by ADR-004.

    Classes without metrics (``extraction_mode != "ast"``) are placed into
    the *mid* bucket so they are not unfairly promoted or demoted.

``SelectionResult`` is the frozen value object returned by ``select()``.  Its
8 base fields are described in ADR-009; the 3 ADR-010 Fork 9 extension fields
support the unsupported-feature policy machinery in the TypeScript renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeograph.graph.models.graph_schema import ClassNode, CodeographKnowledgeGraph
    from codeograph.rendering.domain_grouping import DomainGrouping

__all__ = ["ClassSelector", "SelectionResult"]

# ---------------------------------------------------------------------------
# ADR-009 thresholds (Lanza & Marinescu 2006, pp 16-18)
# ---------------------------------------------------------------------------
_HIGH_CBO_THRESHOLD = 5  # CBO ≥ this → OR-high bucket
_HIGH_WMC_THRESHOLD = 20  # WMC ≥ this → OR-high bucket
_LOW_CBO_THRESHOLD = 1  # CBO ≤ this → candidate for OR-low
_LOW_WMC_THRESHOLD = 5  # WMC ≤ this → candidate for OR-low (AND with CBO)

# Default per-group budget cap (overridden by TypeScriptConfig.render_budget)
_DEFAULT_CAP = 50


# ---------------------------------------------------------------------------
# SelectionResult — frozen value object (ADR-009 + ADR-010 Fork 9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of one ``ClassSelector.select()`` call (ADR-009).

    Base fields (8):
        selected:       Classes that passed the selection ladder and will be
                        rendered by the LLM.
        excluded:       Classes present in the graph but not selected due to
                        the budget cap.
        strategy:       Which tier was applied: ``"take_all"``,
                        ``"top_n_v1"``, or ``"stratified_threshold_v1"``.
        group_name:     The domain-group label this result covers.
        cap:            The per-group budget cap that was applied.
        total_in_group: Total classes in the group before selection.
        metrics_missing_count: Classes without CBO/WMC metrics (placed in
                        mid-bucket for stratified; listed for observability).
        high_count:     Classes placed in the OR-high bucket (stratified only;
                        0 for other tiers).

    ADR-010 Fork 9 extension fields (3):
        refused:        Classes excluded because ``security_feature_policy``
                        or ``webflux_policy`` triggered a ``"refuse"`` decision.
        stub_todos:     Classes that will be rendered as stub-with-TODO because
                        a feature policy triggered ``"stub_todo"``.
        feature_policies_active: Names of the feature policies that fired
                        during this selection pass.
    """

    # -- base fields --------------------------------------------------------
    selected: tuple[str, ...]
    excluded: tuple[str, ...]
    strategy: str
    group_name: str
    cap: int
    total_in_group: int
    metrics_missing_count: int
    high_count: int

    # -- ADR-010 Fork 9 extension fields ------------------------------------
    refused: tuple[str, ...] = field(default_factory=tuple)
    stub_todos: tuple[str, ...] = field(default_factory=tuple)
    feature_policies_active: tuple[str, ...] = field(default_factory=tuple)


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
            from codeograph.rendering.domain_grouping import PackagePrefixGrouping

            self._grouping: DomainGrouping = PackagePrefixGrouping()
        else:
            self._grouping = grouping

    def select(self, graph: CodeographKnowledgeGraph) -> list[SelectionResult]:
        """Run the selection ladder over all domain groups in *graph*.

        Returns:
            One ``SelectionResult`` per domain group, in ascending group-name
            order.  Groups with zero classes are omitted.
        """
        class_nodes = self._extract_class_nodes(graph)
        if not class_nodes:
            return []

        all_fqcns = [n.id for n in class_nodes]
        self._grouping.prepare(all_fqcns)

        # Bucket by group
        groups: dict[str, list[ClassNode]] = {}
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

    def _extract_class_nodes(self, graph: CodeographKnowledgeGraph) -> list[ClassNode]:
        """Return only the ClassNode entries from *graph*."""
        from codeograph.graph.models.graph_schema import ClassNode as CN

        out: list[ClassNode] = []
        for node_wrapper in graph.nodes:
            node = node_wrapper.root
            if isinstance(node, CN):
                out.append(node)
        return out

    def _apply_ladder(self, group_name: str, members: list[ClassNode]) -> SelectionResult:
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

    def _top_n_v1(self, group_name: str, members: list[ClassNode], cap: int, total: int) -> SelectionResult:
        """Tier 2: sort descending by WMC, take top ``cap``."""
        sorted_members = sorted(members, key=lambda m: (m.wmc is None, -(m.wmc or 0)))
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
        self, group_name: str, members: list[ClassNode], cap: int, total: int
    ) -> SelectionResult:
        """Tier 3: bucket into high/mid/low, fill proportionally.

        Thresholds (Lanza & Marinescu 2006, pp 16-18):
            OR-high : CBO ≥ 5  OR  WMC ≥ 20
            OR-low  : CBO ≤ 1  AND WMC ≤ 5
            mid     : everything else (including metrics-missing classes)
        """
        high: list[ClassNode] = []
        mid: list[ClassNode] = []
        low: list[ClassNode] = []
        missing_metrics = 0

        for m in members:
            if m.cbo is None or m.wmc is None:
                missing_metrics += 1
                mid.append(m)
                continue
            if m.cbo >= _HIGH_CBO_THRESHOLD or m.wmc >= _HIGH_WMC_THRESHOLD:
                high.append(m)
            elif m.cbo <= _LOW_CBO_THRESHOLD and m.wmc <= _LOW_WMC_THRESHOLD:
                low.append(m)
            else:
                mid.append(m)

        # Sort each bucket by descending WMC (nulls last).
        def _wmc_key(m: ClassNode) -> tuple[bool, int]:
            return (m.wmc is None, -(m.wmc or 0))

        high.sort(key=_wmc_key)
        mid.sort(key=_wmc_key)
        low.sort(key=_wmc_key)

        # Fill cap: high → mid → low
        selected: list[ClassNode] = []
        for bucket in (high, mid, low):
            remaining = cap - len(selected)
            if remaining <= 0:
                break
            selected.extend(bucket[:remaining])

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


def _count_missing_metrics(members: list[ClassNode]) -> int:
    return sum(1 for m in members if m.cbo is None or m.wmc is None)
