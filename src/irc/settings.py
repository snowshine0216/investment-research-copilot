from __future__ import annotations
from pydantic import Field
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

    # Required
    deepseek_api_key: str = Field(min_length=1)
    openrouter_api_key: str = Field(min_length=1)

    # Optional (LDR)
    ldr_base_url: str = "http://localhost:8080"
    ldr_api_token: str = ""

    # Optional (OpenBB extras)
    openbb_fmp_key: str = ""
    openbb_tiingo_key: str = ""

    # Roadmap (declared so .env doesn't error on extras)
    tushare_token: str = ""
    anthropic_api_key: str = ""
