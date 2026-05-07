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


def test_settings_missing_deepseek_fails(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_optional_fields_default_empty(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    s = Settings(_env_file=None)
    assert s.openbb_fmp_key == ""
    assert s.tushare_token == ""
