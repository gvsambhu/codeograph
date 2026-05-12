from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

_CONFIG_YAML = Path("config.yaml")


class YamlConfigSource(PydanticBaseSettingsSource):
    """Loads settings from config.yaml in the current working directory.

    Lowest-priority source — env vars and .env always override.
    Never store secrets here.
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> Any:
        return self._load().get(field_name)

    def __call__(self) -> dict[str, Any]:
        return self._load()

    @staticmethod
    def _load() -> dict[str, Any]:
        if not _CONFIG_YAML.exists():
            return {}
        with _CONFIG_YAML.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
