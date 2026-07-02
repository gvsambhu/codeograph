from pathlib import Path
from tempfile import NamedTemporaryFile

from codeograph.llm.price_loader import PriceLoader, PriceRecord


def test_price_loader_success():
    """Verify that PriceLoader correctly loads a valid TOML and performs queries."""
    toml_content = """
[metadata]
capture_date = "2026-06-26"
staleness_window_days = 90

[prices]
"a.b" = { input_usd_per_million = 3.0, output_usd_per_million = 15.0, cache_read_usd_per_million = 0.3 }
"g.p" = { input_usd_per_million = 2.0, output_usd_per_million = 12.0, cache_read_usd_per_million = 0.0 }
"""
    with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.close()
        temp_path = Path(f.name)

    try:
        loader = PriceLoader(temp_path)

        metadata = loader.get_metadata()
        assert metadata == {
            "capture_date": "2026-06-26",
            "staleness_window_days": 90,
        }

        prices = loader.load_prices()
        assert len(prices) == 2
        assert prices["a.b"] == PriceRecord(
            input_usd_per_million=3.0,
            output_usd_per_million=15.0,
            cache_read_usd_per_million=0.3,
        )
        assert prices["g.p"] == PriceRecord(
            input_usd_per_million=2.0,
            output_usd_per_million=12.0,
            cache_read_usd_per_million=0.0,
        )

        assert loader.get_price("a", "b") == PriceRecord(
            input_usd_per_million=3.0,
            output_usd_per_million=15.0,
            cache_read_usd_per_million=0.3,
        )

        assert loader.get_price("A", "B") == PriceRecord(
            input_usd_per_million=3.0,
            output_usd_per_million=15.0,
            cache_read_usd_per_million=0.3,
        )

        assert loader.get_price("missing", "model") is None
    finally:
        temp_path.unlink()
