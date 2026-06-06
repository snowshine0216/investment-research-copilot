"""ask command, with LLM call faked, records actuals for interactive_query."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from irc.llm._types import ChatResponse


@pytest.fixture
def ask_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config/spend_pricing.yaml").write_text(
        yaml.safe_dump({
            "margin": 1.2,
            "llm": {
                "deepseek": {
                    "currency": "CNY",
                    "models": {
                        "deepseek-chat": {
                            "input_per_mtok": 1.0,
                            "output_per_mtok": 2.0,
                        },
                    },
                },
            },
            "seeds": {
                "interactive_query": {
                    "calls": 2,
                    "prompt_tokens": 2000,
                    "completion_tokens": 600,
                },
            },
        }),
        encoding="utf-8",
    )
    (tmp_path / "config/spend_balances.yaml").write_text(
        yaml.safe_dump({}), encoding="utf-8",
    )
    (tmp_path / "outputs" / "2026-06-06").mkdir(parents=True)
    return tmp_path


def test_ask_run_records_interactive_query_samples_0_to_1(ask_repo, monkeypatch):
    """Shape A: respond_to_query returns ChatResponse; run_ask appends CostEntry and records."""
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")
    monkeypatch.setattr(
        "irc.queries.responder.call_chat",
        lambda **kw: ChatResponse(
            text="黄金 regime=risk_on", prompt_tokens=800, completion_tokens=200,
        ),
    )
    # Stub load_repo_configs to avoid needing full config in tmp_path
    import irc.commands.ask_cmd as ask_mod
    from irc.llm._types import ResolvedRoute

    fake_route = ResolvedRoute(
        task="interactive_query",
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    )

    class _FakeBundle:
        llm = None

    monkeypatch.setattr(ask_mod, "load_repo_configs", lambda _root: _FakeBundle())
    monkeypatch.setattr(ask_mod, "resolve_route", lambda task, llm: fake_route)
    # Stub _today to fix date
    monkeypatch.setattr(ask_mod, "_today", lambda: "2026-06-06")

    rc = ask_mod.run_ask(str(ask_repo), "What is the gold regime?")
    assert rc == 0

    # 1. spend_actuals.json written
    actuals_path = ask_repo / "outputs" / "2026-06-06" / "spend_actuals.json"
    assert actuals_path.exists(), "spend_actuals.json must be written after run_ask"
    actuals = json.loads(actuals_path.read_text())
    assert "interactive_query" in actuals["tasks"]
    assert actuals["tasks"]["interactive_query"]["avg_prompt_tokens"] == 800.0

    # 2. usage_profile.json samples 0→1
    prof_path = ask_repo / "data" / "spend" / "usage_profile.json"
    assert prof_path.exists(), "usage_profile.json must be written"
    prof = json.loads(prof_path.read_text())
    assert prof["interactive_query"]["samples"] == 1
    # 3. EWMA moved toward actual: 0.3 * 800 + 0.7 * 2000 = 1640
    assert prof["interactive_query"]["avg_prompt_tokens"] == pytest.approx(1640.0)
