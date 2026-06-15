from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.settings import Settings


def test_settings_loads_required_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    s = Settings(_env_file=None)
    # SecretStr: access via .get_secret_value()
    assert s.deepseek_api_key.get_secret_value() == "sk-test-deepseek"
    assert s.openrouter_api_key.get_secret_value() == "sk-or-test"
    # repr must NOT expose raw key
    assert "sk-test-deepseek" not in repr(s)
    assert "sk-or-test" not in repr(s)


def test_settings_missing_deepseek_constructs_with_empty_default(monkeypatch):
    # deepseek_api_key is now Optional (validated at call edge, not at construction time).
    # See Task 18: both provider keys default to "" and raise only when the task resolves
    # to that provider and _resolve_key finds the env var absent.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    s = Settings(_env_file=None)
    assert s.deepseek_api_key.get_secret_value() == ""


def test_settings_optional_fields_default_empty(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    # Clear optional keys that the user's local .env may have populated.
    for key in ("OPENBB_FMP_KEY", "OPENBB_TIINGO_KEY", "TUSHARE_TOKEN",
                "TAVILY_API_KEY", "BRAVE_API_KEY", "BOCHA_API_KEY", "JINA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.openbb_fmp_key.get_secret_value() == ""
    assert s.tushare_token.get_secret_value() == ""


from pydantic import SecretStr


def test_provider_secrets_are_secretstr(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-xxx")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-xxx")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    monkeypatch.setenv("TUSHARE_TOKEN", "tu-xxx")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-xxx")
    monkeypatch.setenv("BRAVE_API_KEY", "brv-xxx")
    monkeypatch.setenv("BOCHA_API_KEY", "bocha-xxx")
    monkeypatch.setenv("JINA_API_KEY", "jina-xxx")
    monkeypatch.setenv("OPENBB_FMP_KEY", "fmp-xxx")
    monkeypatch.setenv("OPENBB_TIINGO_KEY", "tg-xxx")
    from irc.settings import Settings
    s = Settings(_env_file=None)
    for name in ("anthropic_api_key", "tushare_token",
                 "tavily_api_key", "brave_api_key", "bocha_api_key", "jina_api_key",
                 "openbb_fmp_key", "openbb_tiingo_key"):
        assert isinstance(getattr(s, name), SecretStr)
        assert str(getattr(s, name)) == "**********"


def test_openrouter_missing_returns_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    from irc.settings import Settings
    s = Settings(_env_file=None)
    assert s.openrouter_api_key.get_secret_value() == ""
