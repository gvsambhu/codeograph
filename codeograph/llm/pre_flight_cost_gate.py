"""Pre-flight cost gate: estimate → echo → confirm (ADR-027 Fork 2/3/4, SRP-01 extraction)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from codeograph.config.settings import Settings
    from codeograph.manifest.artefact import GraphArtefact

__all__ = ["PreFlightCostGate"]


class PreFlightCostGate:
    """Reads the graph, estimates cost, echoes the estimate, and calls ConfirmationGate.

    Encapsulates the pre-flight sequence that was previously inlined in
    ``cli/main.py::run`` so the run handler delegates in one call rather than
    assembling the estimator chain itself.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check(
        self,
        graph_artefact: GraphArtefact,
        yes: bool,
        non_interactive: bool,
    ) -> None:
        """Estimate cost from *graph_artefact*, echo the estimate, and confirm.

        Raises :class:`click.Abort` if the user rejects a TTY prompt.
        Raises :class:`click.ClickException` if the threshold is exceeded in a
        non-interactive run without a waiver flag.
        """
        from codeograph.llm.confirmation_gate import ConfirmationGate
        from codeograph.llm.pre_flight_estimator import PreFlightEstimator
        from codeograph.llm.price_loader import PriceLoader

        settings = self._settings

        with graph_artefact.path.open("r", encoding="utf-8") as fh:
            graph_data = json.load(fh)
        node_count = len(graph_data.get("nodes", []))

        # PriceLoader() defaults to prices.toml co-located with the llm package.
        estimator = PreFlightEstimator(PriceLoader())
        estimate = estimator.estimate_cost(
            node_count=node_count,
            provider_label=settings.resolved_provider_label,
            model_name=settings.llm_model,
        )
        click.echo(estimator.format_estimate(estimate))

        ConfirmationGate(settings.llm_call_confirm_threshold).check(
            total_calls=estimate.total_calls,
            yes=yes,
            non_interactive=non_interactive,
        )
