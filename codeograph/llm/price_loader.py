import tomllib
from pathlib import Path
from typing import Any, NamedTuple


class PriceRecord(NamedTuple):
    input_usd_per_million: float
    output_usd_per_million: float
    cache_read_usd_per_million: float


class PriceLoader:
    """Loads and queries pricing data from prices.toml for cost estimation."""

    def __init__(self, toml_path: Path | None = None) -> None:
        if toml_path is None:
            self._toml_path = Path(__file__).parent / "prices.toml"
        else:
            self._toml_path = toml_path
        self._prices = self.load_prices()

    def load_prices(self) -> dict[str, PriceRecord]:
        """Load and parse the prices table from the TOML file.

        Returns:
            dict[str, PriceRecord]: Map of "{provider_label}.{model}" -> PriceRecord
        """
        with self._toml_path.open("rb") as f:
            data = tomllib.load(f)

        raw_prices = data.get("prices")
        if raw_prices is None:
            raise ValueError("Missing required [prices] section in prices TOML.")
        if not isinstance(raw_prices, dict):
            raise ValueError("The [prices] section must be a TOML table.")

        prices: dict[str, PriceRecord] = {}

        for key, raw_record in raw_prices.items():
            if not isinstance(key, str):
                raise ValueError(f"Invalid price key {key!r}; expected string.")
            if not isinstance(raw_record, dict):
                raise ValueError(f"Price entry {key!r} must be an inline table.")

            try:
                prices[key] = PriceRecord(**raw_record)
            except TypeError as e:
                raise ValueError(
                    f"Invalid price record for {key!r}: expected fields "
                    "input_usd_per_million, output_usd_per_million, "
                    "cache_read_usd_per_million."
                ) from e

        return prices

    def get_price(self, provider_label: str, model: str) -> PriceRecord | None:
        """Retrieve price record for a given provider label and model name.

        Normalizes inputs to lowercase before performing the lookup.

        Returns:
            PriceRecord | None: The price record if found, else None.
        """
        key = f"{provider_label.strip().lower()}.{model.strip().lower()}"
        return self._prices.get(key)

    def get_metadata(self) -> dict[str, Any]:
        """Retrieve metadata block (capture_date, staleness_window_days).

        Returns:
            dict[str, Any]: Dict containing metadata properties.
        """
        with self._toml_path.open("rb") as f:
            data = tomllib.load(f)

        metadata = data.get("metadata")
        if metadata is None:
            raise ValueError("Missing required [metadata] section in prices TOML.")
        if not isinstance(metadata, dict):
            raise ValueError("The [metadata] section must be a TOML table.")

        return metadata