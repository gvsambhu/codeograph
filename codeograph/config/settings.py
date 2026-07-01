from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from codeograph.config.yaml_source import YamlConfigSource
from codeograph.llm.models import ProviderType, Tier

_DEFAULT_JAR = Path(__file__).parent.parent / "parser" / "lib" / "parser.jar"


class Settings(BaseSettings):
    """Application-wide configuration.

    Priority (highest → lowest): init kwargs > env vars > .env > config.yaml > defaults.
    All env vars are prefixed CODEOGRAPH_ (e.g. CODEOGRAPH_LLM_CONCURRENCY=10).
    Secrets must be supplied via env or .env only — never in config.yaml.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CODEOGRAPH_",
        env_nested_delimiter="__",
        populate_by_name=True,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # LLM
    # -------------------------------------------------------------------------

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CODEOGRAPH_ANTHROPIC_API_KEY"),
        description="Anthropic API key. Set via ANTHROPIC_API_KEY or CODEOGRAPH_ANTHROPIC_API_KEY.",
    )
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "CODEOGRAPH_OPENROUTER_API_KEY"),
        description="OpenRouter API key. Set via OPENROUTER_API_KEY or CODEOGRAPH_OPENROUTER_API_KEY.",
    )
    openai_compat_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CODEOGRAPH_OPENAI_COMPAT_API_KEY"),
        description="OpenAI-compatible API key. Set via CODEOGRAPH_OPENAI_COMPAT_API_KEY.",
    )
    openai_compat_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CODEOGRAPH_OPENAI_COMPAT_BASE_URL"),
        description="OpenAI-compatible base URL. Set via CODEOGRAPH_OPENAI_COMPAT_BASE_URL.",
    )
    openai_compat_provider_label: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL"),
        description="Optional provider label (e.g. 'groq'). Set via CODEOGRAPH_OPENAI_COMPAT_PROVIDER_LABEL.",
    )
    llm_provider: ProviderType = Field(
        default=ProviderType.ANTHROPIC,
        description="LLM provider: anthropic | openrouter | openai_compatible | ollama | bedrock.",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-6",
        description="Exact model identifier used for all LLM calls in v1 (ADR-005 M1).",
    )
    llm_model_fast: str | None = Field(
        default=None,
        description="Optional FAST-tier model override.",
    )
    llm_model_deep: str | None = Field(
        default=None,
        description="Optional DEEP-tier model override.",
    )
    llm_model_render: str | None = Field(
        default=None,
        description="Optional RENDER-tier model override.",
    )
    llm_call_confirm_threshold: int = Field(
        default=100,
        description="Threshold of estimated calls above which confirmation is required.",
    )
    max_llm_calls: int | None = Field(
        default=None,
        description="Maximum number of LLM calls permitted in a single run.",
    )
    max_tokens_total: int | None = Field(
        default=None,
        description="Maximum number of tokens permitted across a single run.",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for Ollama API.",
    )
    bedrock_region: str | None = Field(
        default=None,
        description="Optional AWS region for Bedrock runtime.",
    )
    llm_concurrency: int = Field(
        default=5,
        description="Maximum concurrent LLM calls (ADR-005).",
    )
    max_pass1_failure_ratio: float = Field(
        default=0.10,
        description=("Fraction of Pass 1 calls allowed to fail before the run aborts (ADR-005). Range: 0.0–1.0."),
    )

    # -------------------------------------------------------------------------
    # Cache
    # -------------------------------------------------------------------------

    cache_dir: Path = Field(
        default=Path.home() / ".codeograph" / "cache",
        description="Directory for the SQLite cache.db and telemetry JSONL files.",
    )
    cache_warn_size_mb: int = Field(
        default=1024,
        description="Emit advisory warning if cache.db size exceeds this limit in MB.",
    )
    cache_warn_entry_count: int = Field(
        default=50000,
        description="Emit advisory warning if cache.db entry count exceeds this limit.",
    )

    # -------------------------------------------------------------------------
    # Parser
    # -------------------------------------------------------------------------

    javaparser_jar: Path = Field(
        default=_DEFAULT_JAR,
        description="Path to the bundled JavaParser JAR. Override to use a custom build.",
    )

    @field_validator("llm_concurrency")
    @classmethod
    def validate_llm_concurrency(cls, v: int) -> int:
        if not (1 <= v <= 50):
            raise ValueError(f"llm_concurrency must be between 1 and 50, got {v}.")
        return v

    @field_validator("max_pass1_failure_ratio")
    @classmethod
    def validate_max_pass1_failure_ratio(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"max_pass1_failure_ratio must be between 0.0 and 1.0, got {v}.")
        return v

    @model_validator(mode="after")
    def validate_openai_compat_settings(self) -> Settings:
        if self.llm_provider == ProviderType.OPENAI_COMPATIBLE:
            if not self.openai_compat_base_url:
                raise ValueError(
                    "openai_compat_base_url is required when "
                    "llm_provider is 'openai_compatible'."
                )
            if not (
                self.openai_compat_base_url.startswith("http://")
                or self.openai_compat_base_url.startswith("https://")
            ):
                raise ValueError(
                    "openai_compat_base_url must start with "
                    f"'http://' or 'https://', got {self.openai_compat_base_url!r}."
                )
        return self

    @model_validator(mode="after")
    def validate_javaparser_jar_exists(self) -> Settings:
        import warnings

        # If the file doesn't exist, log a warning rather than crashing.
        # This handles ast-only bypass logic happening in the CLI, where the jar
        # is only required if a Java file actually needs to be parsed natively.
        if not self.javaparser_jar.exists():
            warnings.warn(f"javaparser_jar not found at {self.javaparser_jar}. Parsing may fail.")
        return self

    @property
    def resolved_provider_label(self) -> str:
        """Derive endpoint identity / provider label per D-013-7 / D-001-5.

        Falls back to hostname-derived label when no explicit label is set.
        Common host→label aliases map hostnames to the price-table keys in
        ``prices.toml`` so the pre-flight estimator can find prices.
        """
        if self.llm_provider == ProviderType.OPENAI_COMPATIBLE:
            if self.openai_compat_provider_label:
                return self.openai_compat_provider_label
            if self.openai_compat_base_url:
                from urllib.parse import urlparse
                parsed = urlparse(self.openai_compat_base_url)
                host = (parsed.hostname or parsed.netloc or "").lower()
                hostname = host.split(":")[0]
                host_to_label: dict[str, str] = {
                    "api.deepseek.com": "deepseek",
                    "api.minimax.chat": "minimax",
                    "api.minimaxi.com": "minimax",
                    "api.moonshot.cn": "moonshot",
                    "open.bigmodel.cn": "z.ai",
                    "api.mistral.ai": "mistral",
                    "api.openai.com": "openai",
                    "api.anthropic.com": "anthropic",
                    "generativelanguage.googleapis.com": "google",
                    "openrouter.ai": "openrouter",
                }
                return host_to_label.get(hostname, hostname)
            return "openai_compatible"
        return self.llm_provider.value

    @property
    def tier_map(self) -> dict[Tier, str]:
        """Return the resolved model→tier mapping used by provider dispatch."""
        return {
            Tier.FAST: self.llm_model_fast or self.llm_model,
            Tier.DEEP: self.llm_model_deep or self.llm_model,
            Tier.RENDER: self.llm_model_render or self.llm_model,
        }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority order per ADR-001:
        # init kwargs > env vars > .env file > config.yaml > pydantic defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSource(settings_cls),
        )
