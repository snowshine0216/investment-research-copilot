from __future__ import annotations
import pytest
from irc.settings import Settings


def test_settings_loads_required_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    s = Settings()
    assert s.deepseek_api_key == "sk-test-deepseek"
    assert s.openrouter_api_key == "sk-or-test"


def test_settings_missing_deepseek_fails(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    with pytest.raises(Exception):
        Settings()


def test_settings_optional_fields_default_empty(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    s = Settings()
    assert s.openbb_fmp_key == ""
    assert s.tushare_token == ""
