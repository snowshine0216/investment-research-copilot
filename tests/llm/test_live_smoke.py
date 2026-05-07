"""Live smoke tests for the LLM gateway. Skipped unless RUN_LIVE_LLM_TESTS=1
AND the relevant API key env vars are set. Used to verify production credentials
and provider URL mapping. Do not run in CI by default."""
from __future__ import annotations
import os
import pytest

from irc.config_loader import load_yaml
from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat
from pathlib import Path


_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_HAS_DS = bool(os.environ.get("DEEPSEEK_API_KEY"))
_HAS_OR = bool(os.environ.get("OPENROUTER_API_KEY"))


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_deepseek_chat():
    cfg_path = Path(__file__).resolve().parents[2] / "src/irc/templates/config/llm.yaml"
    # bypass repo-relative resolver: load via direct schema
    import yaml
    from irc.schemas.llm import LLMConfig
    cfg = LLMConfig.model_validate(yaml.safe_load(cfg_path.read_text()))
    route = resolve_route("news_summary", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with the single word: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()


@pytest.mark.skipif(not (_RUN and _HAS_OR), reason="set RUN_LIVE_LLM_TESTS=1 + OPENROUTER_API_KEY")
def test_live_openrouter_claude():
    cfg_path = Path(__file__).resolve().parents[2] / "src/irc/templates/config/llm.yaml"
    import yaml
    from irc.schemas.llm import LLMConfig
    cfg = LLMConfig.model_validate(yaml.safe_load(cfg_path.read_text()))
    route = resolve_route("memo_audit", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()
