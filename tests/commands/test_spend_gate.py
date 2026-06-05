from datetime import date
from pathlib import Path
from irc.commands.spend_cmd import preflight_gate, collect_api_keys

REPO = Path(__file__).resolve().parents[2]


def test_collect_api_keys_only_includes_set_keys(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-d")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    keys = collect_api_keys()
    assert keys.get("deepseek") == "sk-d"
    assert "openrouter" not in keys


def test_preflight_gate_blocks_with_env_flag(monkeypatch):
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")
    # when skipped, gate returns 0 regardless
    rc = preflight_gate(str(REPO), "memo", today=date(2026, 6, 5))
    assert rc == 0
