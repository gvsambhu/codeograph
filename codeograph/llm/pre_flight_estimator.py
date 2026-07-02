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
    provider_label: str
    model_name: str


class PreFlightEstimator:
    """Estimates LLM calls and indicative USD costs prior to pipeline execution."""

    # Heuristic token estimates — deliberately rough operational numbers, not
    # empirically calibrated. Grounded in ADR-005 D-005-4's ~4 chars/token
    # estimate; actual token counts vary with prompt content and class size.
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
        if current_date is None:
            current_date = date.today()

        total_calls = node_count + 1

        metadata = self._price_loader.get_metadata()
        price_date = metadata.get("capture_date")
        if price_date is not None and not isinstance(price_date, str):
            price_date = str(price_date)
        staleness_window_days = int(metadata.get("staleness_window_days", 90))

        is_staleness_warning = False
        if price_date:
            capture_date = date.fromisoformat(price_date)
            age_days = (current_date - capture_date).days
            is_staleness_warning = age_days > staleness_window_days

        price = self._price_loader.get_price(provider_label, model_name)
        if price is None:
            return CostEstimate(
                total_calls=total_calls,
                estimated_cost_usd=None,
                price_date=price_date,
                is_free=False,
                is_staleness_warning=is_staleness_warning,
                is_unknown_model=True,
                provider_label=provider_label,
                model_name=model_name,
            )

        pass1_input_tokens = node_count * self.PASS1_EST_INPUT_TOKENS_PER_CLASS
        pass1_output_tokens = node_count * self.PASS1_EST_OUTPUT_TOKENS_PER_CLASS
        pass2_input_tokens = self.PASS2_EST_INPUT_TOKENS
        pass2_output_tokens = self.PASS2_EST_OUTPUT_TOKENS

        pass1_cost = (pass1_input_tokens / 1_000_000) * price.input_usd_per_million + (
            pass1_output_tokens / 1_000_000
        ) * price.output_usd_per_million
        pass2_cost = (pass2_input_tokens / 1_000_000) * price.input_usd_per_million + (
            pass2_output_tokens / 1_000_000
        ) * price.output_usd_per_million

        estimated_cost_usd = pass1_cost + pass2_cost
        is_free = estimated_cost_usd == 0.0

        return CostEstimate(
            total_calls=total_calls,
            estimated_cost_usd=estimated_cost_usd,
            price_date=price_date,
            is_free=is_free,
            is_staleness_warning=is_staleness_warning,
            is_unknown_model=False,
            provider_label=provider_label,
            model_name=model_name,
        )

    def format_estimate(self, estimate: CostEstimate) -> str:
        """Format CostEstimate into a user-facing CLI status message.

        Must include the mandatory ADR-027 Fork 4 disclaimer:
        "estimate from a dated price table, not a quote — actual cost depends on model,
        caching, and provider pricing; verify before relying."

        Returns:
            str: The user-friendly formatted warning or estimate.
        """
        disclaimer = (
            "estimate from a dated price table, not a quote — actual cost depends on model, "
            "caching, and provider pricing; verify before relying."
        )

        if estimate.is_unknown_model:
            message = (
                f"Pre-flight Cost Estimate: {estimate.total_calls} calls "
                f"(cost estimate unavailable: no price data found "
                f"for model '{estimate.model_name}' on provider '{estimate.provider_label}')"
            )
        else:
            cost_str = (
                f"${estimate.estimated_cost_usd:.2f} USD" if estimate.estimated_cost_usd is not None else "unavailable"
            )
            message = (
                f"Pre-flight Cost Estimate: {cost_str} "
                f"({estimate.total_calls} calls, price data from {estimate.price_date})"
            )

        if estimate.is_staleness_warning:
            message += " WARNING: price table may be stale."

        return f"{message} — {disclaimer}"
