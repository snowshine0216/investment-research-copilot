"""Live smoke tests for the LLM gateway. Skipped unless RUN_LIVE_LLM_TESTS=1
AND the relevant API key env vars are set. Used to verify production credentials
and provider URL mapping. Do not run in CI by default."""
from __future__ import annotations
import os
import pytest
from importlib import resources
import yaml

from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat
from irc.schemas.llm import LLMConfig


_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_HAS_DS = bool(os.environ.get("DEEPSEEK_API_KEY"))
_HAS_OR = bool(os.environ.get("OPENROUTER_API_KEY"))


def _load_llm_config() -> LLMConfig:
    text = resources.files("irc.templates.config").joinpath("llm.yaml").read_text(encoding="utf-8")
    return LLMConfig.model_validate(yaml.safe_load(text))


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_deepseek_chat():
    cfg = _load_llm_config()
    route = resolve_route("news_summary", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with the single word: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()


@pytest.mark.skipif(not (_RUN and _HAS_OR), reason="set RUN_LIVE_LLM_TESTS=1 + OPENROUTER_API_KEY")
def test_live_openrouter_claude():
    cfg = _load_llm_config()
    route = resolve_route("memo_audit", cfg)
    resp = call_chat(route, messages=[{"role": "user", "content": "Reply with: pong"}], timeout_s=30)
    assert "pong" in resp.text.lower()
