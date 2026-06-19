"""SelectionResult — frozen value object for class selection (ADR-009 + ADR-010)."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SelectionResult"]


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
