from pathlib import Path
from tempfile import NamedTemporaryFile

from codeograph.llm.price_loader import PriceLoader


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
        loader = PriceLoader(temp_path)  # noqa: F841
        # TODO(learner): Add the assertions to verify:
        # 1. loader.get_metadata() returns correct metadata mapping.
        # 2. loader.load_prices() populates all records correctly.
        # 3. loader.get_price("a", "b") returns matching PriceRecord.
        # 4. Lookup is case-insensitive (e.g. get_price("A", "B")).
        # 5. Non-existent provider/model lookup returns None.
        pass
    finally:
        temp_path.unlink()
