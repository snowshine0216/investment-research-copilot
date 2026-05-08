from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import pytest
from irc.llm.http_client import ChatResponse
from irc.commands.init_cmd import run_init
from irc.commands.ask_cmd import run_ask
from irc.queries.parser import parse_query


def _resp(text: str) -> ChatResponse:
    return ChatResponse(text=text, prompt_tokens=5, completion_tokens=10, latency_ms=30, raw={})


def test_parse_query_bullish_intent():
    q = parse_query("518880 为什么看多？")
    assert q.intent == "bullish"
    assert "518880" in q.instruments_mentioned


def test_parse_query_info_intent():
    q = parse_query("黄金现在贵吗？")
    assert q.intent == "info"


def test_ask_command_returns_zero(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    with patch("irc.queries.responder.call_chat", return_value=_resp("回答内容")):
        rc = run_ask(str(tmp_path), "黄金现在贵吗？")
    assert rc == 0
