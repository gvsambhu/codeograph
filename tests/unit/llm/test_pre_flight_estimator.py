from datetime import date  # noqa: F401
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from codeograph.llm.pre_flight_estimator import PreFlightEstimator
from codeograph.llm.price_loader import PriceLoader


def test_pre_flight_estimator():
    """Verify that PreFlightEstimator performs correct calculations and warning triggers."""
    toml_content = """
[metadata]
capture_date = "2026-06-26"
staleness_window_days = 90

[prices]
"a.b" = { input_usd_per_million = 3.0, output_usd_per_million = 15.0, cache_read_usd_per_million = 0.3 }
"g.f" = { input_usd_per_million = 0.0, output_usd_per_million = 0.0, cache_read_usd_per_million = 0.0 }
"""
    with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.close()
        temp_path = Path(f.name)

    try:
        loader = PriceLoader(temp_path)
        estimator = PreFlightEstimator(loader)

        est = estimator.estimate_cost(10, "a", "b", date(2026, 7, 1))
        assert est.total_calls == 11
        assert est.estimated_cost_usd == pytest.approx(0.159, abs=1e-9)
        assert est.is_staleness_warning is False
        assert est.is_unknown_model is False
        assert est.is_free is False
        assert est.price_date == "2026-06-26"
        assert est.provider_label == "a"
        assert est.model_name == "b"

        stale_est = estimator.estimate_cost(10, "a", "b", date(2026, 12, 1))
        assert stale_est.is_staleness_warning is True

        unknown_est = estimator.estimate_cost(10, "a", "unknown-model", date(2026, 7, 1))
        assert unknown_est.estimated_cost_usd is None
        assert unknown_est.is_unknown_model is True
        assert unknown_est.total_calls == 11
        assert unknown_est.is_free is False
        assert unknown_est.provider_label == "a"
        assert unknown_est.model_name == "unknown-model"

        free_est = estimator.estimate_cost(10, "g", "f", date(2026, 7, 1))
        assert free_est.estimated_cost_usd == pytest.approx(0.0, abs=1e-12)
        assert free_est.is_free is True
        assert free_est.is_unknown_model is False

        formatted = estimator.format_estimate(est)
        assert "Pre-flight Cost Estimate:" in formatted
        assert "$0.16 USD" in formatted
        assert "11 calls" in formatted
        assert "price data from 2026-06-26" in formatted
        assert (
            "estimate from a dated price table, not a quote — actual cost depends on model, "
            "caching, and provider pricing; verify before relying." in formatted
        )

        formatted_stale = estimator.format_estimate(stale_est)
        assert "WARNING" in formatted_stale or "stale" in formatted_stale.lower()

        formatted_unknown = estimator.format_estimate(unknown_est)
        assert "cost estimate unavailable" in formatted_unknown.lower()
        assert "unknown-model" in formatted_unknown
        assert "provider 'a'" in formatted_unknown
    finally:
        temp_path.unlink()
