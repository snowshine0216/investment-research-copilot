"""Acceptance test: settings call-edge routing.

§8 acceptance gate: the LLM routing layer must resolve credentials at the
call edge, not at startup. This means:

- MINIMAX_* present + DEEPSEEK_API_KEY absent → `irc monitor` reaches provider
  routing without raising; the route resolves key/model/base_url correctly.
- DEEPSEEK_API_KEY present + MINIMAX_* absent → legacy tasks (memo_synthesis)
  still route to DeepSeek correctly.

`verify_host_resolves_publicly` is patched to avoid live DNS in unit tests.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from irc.config_loader import load_yaml
from irc.llm.gateway import resolve_route
from irc.llm.http_client import _resolve_base_url, _resolve_key, _resolve_model

REPO = Path(__file__).resolve().parents[2]


def _llm():
    return load_yaml(REPO / "config/llm.yaml", REPO)


def test_monitor_task_routes_with_only_minimax_env(monkeypatch) -> None:
    """MINIMAX_* present, DEEPSEEK absent → monitor route resolves without raising."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "mk")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Text-01")
    r = resolve_route("monitor_impact", _llm())
    assert _resolve_key(r.api_key_env) == "mk"
    assert _resolve_model(r) == "MiniMax-Text-01"
    # Patch DNS check so the test works without live network access.
    with patch("irc.llm.http_client.verify_host_resolves_publicly"):
        base = _resolve_base_url(r)
    assert base.startswith("https://api.minimaxi.com")


def test_legacy_task_routes_with_only_deepseek_env(monkeypatch) -> None:
    """DEEPSEEK_API_KEY present, MINIMAX_* absent → legacy memo_synthesis routes."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dk")
    r = resolve_route("memo_synthesis", _llm())
    assert _resolve_key(r.api_key_env) == "dk"
    assert _resolve_model(r) == "deepseek-reasoner"
    # deepseek uses a literal base_url, but _resolve_base_url still does DNS.
    with patch("irc.llm.http_client.verify_host_resolves_publicly"):
        base = _resolve_base_url(r)
    assert base == "https://api.deepseek.com"
