from datetime import date  # noqa: F401
from pathlib import Path
from tempfile import NamedTemporaryFile

from codeograph.llm.cost_estimator import PreFlightEstimator
from codeograph.llm.price_loader import PriceLoader


def test_cost_estimator():
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
        estimator = PreFlightEstimator(loader)  # noqa: F841

        # TODO(learner): Add assertions for Case 1 (Standard cost calculation):
        # - est = estimator.estimate_cost(10, "a", "b", date(2026, 7, 1))
        # - Assert est.total_calls == 11
        # - Assert est.estimated_cost_usd is close to 0.159
        # - Assert est.is_staleness_warning is False
        # - Assert est.is_unknown_model is False

        # TODO(learner): Add assertions for Case 2 (Staleness warning):
        # - Call estimate with current_date = date(2026, 12, 1)
        # - Assert est.is_staleness_warning is True

        # TODO(learner): Add assertions for Case 3 (Unknown model):
        # - Call estimate with model_name = "unknown-model"
        # - Assert est.estimated_cost_usd is None
        # - Assert est.is_unknown_model is True
        # - Assert est.total_calls == 11

        # TODO(learner): Add assertions for Case 4 (Free tier):
        # - Call estimate with model_name = "f", provider_label="g"
        # - Assert est.estimated_cost_usd == 0.0
        # - Assert est.is_free is True

        # TODO(learner): Verify output format matching ADR-027 Fork 4 rules:
        # - Ensure mandatory disclaimer is present when pricing is available.
        # - Ensure staleness message warning is appended when stale.
        # - Ensure unknown model warning maps correctly.
        pass
    finally:
        temp_path.unlink()
