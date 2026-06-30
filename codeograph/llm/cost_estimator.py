from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from codeograph.llm.price_loader import PriceLoader


@dataclass(frozen=True)
class CostEstimate:
    """Pre-flight cost estimation metrics."""

    total_calls: int
    estimated_cost_usd: float | None
    price_date: str | None
    is_free: bool
    is_staleness_warning: bool
    is_unknown_model: bool


class PreFlightEstimator:
    """Estimates LLM calls and indicative USD costs prior to pipeline execution."""

    # Heuristic average token counts per class/pass to estimate pre-flight volume
    PASS1_EST_INPUT_TOKENS_PER_CLASS: ClassVar[int] = 2000
    PASS1_EST_OUTPUT_TOKENS_PER_CLASS: ClassVar[int] = 400

    PASS2_EST_INPUT_TOKENS: ClassVar[int] = 8000
    PASS2_EST_OUTPUT_TOKENS: ClassVar[int] = 1000

    def __init__(self, price_loader: PriceLoader) -> None:
        self._price_loader = price_loader

    def estimate_cost(
        self,
        node_count: int,
        provider_label: str,
        model_name: str,
        current_date: date | None = None,
    ) -> CostEstimate:
        """Estimate volume and cost.

        Args:
            node_count: Number of annotatable classes in Pass 0.
            provider_label: Resolved label of the provider.
            model_name: Configured model name.
            current_date: Date to evaluate staleness against (defaults to today).

        Returns:
            CostEstimate: Derived estimate data.
        """
        # TODO(learner): Implement cost estimation logic:
        # 1. Derive estimated call count: Pass 1 node annotations (node_count) + 1 Pass 2 synthesis call.
        # 2. Query price record from price_loader by (provider_label, model_name).
        # 3. If price record is missing:
        #    - Set estimated_cost_usd = None, is_unknown_model = True.
        # 4. Otherwise:
        #    - Compute Pass 1 input/output token cost.
        #    - Compute Pass 2 input/output token cost.
        #    - Sum costs to obtain estimated_cost_usd.
        #    - Check if is_free ($0.0 total cost).
        # 5. Evaluate price table metadata and current_date to check if capture date is older
        #    than the staleness_window_days (defaults to 90). If so, set is_staleness_warning = True.
        raise NotImplementedError("To be implemented by the learner.")

    def format_estimate(self, estimate: CostEstimate) -> str:
        """Format CostEstimate into a user-facing CLI status message.

        Must include the mandatory ADR-027 Fork 4 disclaimer:
        "estimate from a dated price table, not a quote — actual cost depends on model,
        caching, and provider pricing; verify before relying."

        Returns:
            str: The user-friendly formatted warning or estimate.
        """
        # TODO(learner): Implement formatting logic:
        # - If is_unknown_model:
        #   "Pre-flight Cost Estimate: {total_calls} calls (cost estimate unavailable: "
        #   "no price data for model '{model_name}' on provider '{provider_label}')"
        # - Else:
        #   "Pre-flight Cost Estimate: ${cost_usd:.2f} USD ({total_calls} calls, price data from {price_date})"
        #   (Append the mandatory disclaimer and any staleness warning if applicable).
        raise NotImplementedError("To be implemented by the learner.")
