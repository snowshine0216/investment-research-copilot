"""Live smoke for the bull/bear debate. Skipped unless RUN_LIVE_LLM_TESTS=1
AND DEEPSEEK_API_KEY set (project live-LLM double-gate)."""
from __future__ import annotations

import json
import os
from importlib import resources

import pytest
import yaml

from irc.llm.gateway import resolve_route
from irc.llm.http_client import call_chat
from irc.opportunity.debate import _DEFEND_SYS, _FALSIFY_SYS
from irc.schemas.llm import LLMConfig

_RUN = os.environ.get("RUN_LIVE_LLM_TESTS") == "1"
_HAS_DS = bool(os.environ.get("DEEPSEEK_API_KEY"))


def _cfg() -> LLMConfig:
    text = resources.files("irc.templates.config").joinpath("llm.yaml").read_text(encoding="utf-8")
    return LLMConfig.model_validate(yaml.safe_load(text))


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_thesis_defend_returns_parseable_json():
    cfg = _cfg()
    route = resolve_route("thesis_defend", cfg)
    assert route.model == "deepseek-reasoner"
    resp = call_chat(route, messages=[
        {"role": "system", "content": _DEFEND_SYS},
        {"role": "user", "content": "name: 测试\nderived_thesis_state: intact\nsummary: 长期逻辑完整\nevidence: 盈利增长"},
    ], timeout_s=60, temperature=0.2)
    data = json.loads(resp.text)
    assert isinstance(data.get("arguments"), list)


@pytest.mark.skipif(not (_RUN and _HAS_DS), reason="set RUN_LIVE_LLM_TESTS=1 + DEEPSEEK_API_KEY")
def test_live_thesis_falsify_returns_parseable_json():
    cfg = _cfg()
    route = resolve_route("thesis_falsify", cfg)
    resp = call_chat(route, messages=[
        {"role": "system", "content": _FALSIFY_SYS},
        {"role": "user", "content": "name: 测试\nderived_thesis_state: intact\nsummary: 长期逻辑完整\nevidence: 盈利增长"},
    ], timeout_s=60, temperature=0.2)
    data = json.loads(resp.text)
    assert isinstance(data.get("conditions"), list)
