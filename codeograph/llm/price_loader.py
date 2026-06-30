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

    def load_prices(self) -> dict[str, PriceRecord]:
        """Load and parse the prices table from the TOML file.

        Returns:
            dict[str, PriceRecord]: Map of "{provider_label}.{model}" -> PriceRecord
        """
        # TODO(learner): Load TOML from self._toml_path using tomllib,
        # parse the "prices" section, and map each key to a PriceRecord.
        raise NotImplementedError("To be implemented by the learner.")

    def get_price(self, provider_label: str, model: str) -> PriceRecord | None:
        """Retrieve price record for a given provider label and model name.

        Normalizes inputs to lowercase before performing the lookup.

        Returns:
            PriceRecord | None: The price record if found, else None.
        """
        # TODO(learner): Resolve f"{provider_label.lower()}.{model.lower()}"
        # against the loaded prices dict. Return the PriceRecord or None.
        raise NotImplementedError("To be implemented by the learner.")

    def get_metadata(self) -> dict[str, Any]:
        """Retrieve metadata block (capture_date, staleness_window_days).

        Returns:
            dict[str, Any]: Dict containing metadata properties.
        """
        # TODO(learner): Load the "metadata" section from the TOML file.
        raise NotImplementedError("To be implemented by the learner.")
