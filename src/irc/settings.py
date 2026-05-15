from __future__ import annotations
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Loads secrets from .env and OS environment. Field names are lowercased
    and read from upper-case env names by pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required — stored as SecretStr so repr(Settings()) never leaks raw values
    deepseek_api_key: SecretStr = Field(min_length=1)

    # Optional
    openrouter_api_key: SecretStr = SecretStr("")

    # Optional (web research — pluggable providers).
    # Configure at least one EN provider (Tavily/Brave) AND one ZH provider (Bocha)
    # for full theme coverage. Jina Reader is the URL → markdown extractor.
    tavily_api_key: SecretStr = SecretStr("")
    brave_api_key: SecretStr = SecretStr("")
    bocha_api_key: SecretStr = SecretStr("")
    jina_api_key: SecretStr = SecretStr("")

    # Optional — set DEBUG=true in .env for verbose logging + full tracebacks.
    debug: bool = False

    # Optional (OpenBB extras)
    openbb_fmp_key: SecretStr = SecretStr("")
    openbb_tiingo_key: SecretStr = SecretStr("")

    # Roadmap (declared so .env doesn't error on extras)
    tushare_token: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
