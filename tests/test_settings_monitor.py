from __future__ import annotations
from irc.settings import Settings


def test_settings_constructs_without_deepseek_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "mk")
    s = Settings(_env_file=None)
    assert s.minimax_api_key.get_secret_value() == "mk"
    assert s.deepseek_api_key.get_secret_value() == ""


def test_settings_constructs_without_minimax_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    s = Settings(_env_file=None)
    assert s.deepseek_api_key.get_secret_value() == "dk"
