from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from codeograph.config.yaml_source import YamlConfigSource

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
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # LLM — unused until DC2; present so the full config surface is visible now
    # -------------------------------------------------------------------------

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key. Set via CODEOGRAPH_ANTHROPIC_API_KEY.",
    )
    llm_provider: str = Field(
        default="anthropic",
        description="LLM provider: anthropic | ollama | bedrock.",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-6",
        description="Exact model identifier used for all LLM calls in v1 (ADR-005 M1).",
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
    # Parser
    # -------------------------------------------------------------------------

    javaparser_jar: Path = Field(
        default=_DEFAULT_JAR,
        description="Path to the bundled JavaParser JAR. Override to use a custom build.",
    )

    # TODO (learner): add @field_validator for llm_provider — must be one of
    #   {"anthropic", "ollama", "bedrock"}; raise ValueError with a clear message otherwise.
    # TODO (learner): add @field_validator for llm_concurrency — enforce a sane range (e.g. 1–50).
    # TODO (learner): add @field_validator for max_pass1_failure_ratio — enforce 0.0 < x <= 1.0.
    # TODO (learner): add @model_validator to check that javaparser_jar exists when
    #   running outside --ast-only mode (or log a warning; decide the policy).
    # TODO (learner): add further fields as M4–M8 reveal the need.

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
