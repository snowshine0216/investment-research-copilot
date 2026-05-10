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
    openrouter_api_key: SecretStr = Field(min_length=1)

    # Optional (LDR)
    ldr_base_url: str = "http://localhost:8080"
    ldr_api_token: SecretStr = SecretStr("")

    # Optional (OpenBB extras)
    openbb_fmp_key: SecretStr = SecretStr("")
    openbb_tiingo_key: SecretStr = SecretStr("")

    # Roadmap (declared so .env doesn't error on extras)
    tushare_token: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
