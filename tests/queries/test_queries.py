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


def test_parse_query_detects_gold_asset_class():
    q = parse_query("现在能入手黄金吗")
    assert q.asset_class == "gold"
    # Gold question must pull memo + scoring + gold-specific snapshots
    assert "memo" in q.context_keys
    assert "gold_regime" in q.context_keys
    assert "gold_band" in q.context_keys


def test_parse_query_detects_us_equity_asset_class():
    q = parse_query("标普500现在能买吗")
    assert q.asset_class == "us_equity"
    assert "memo" in q.context_keys


def test_parse_query_detects_cn_bond_asset_class():
    q = parse_query("政金债现在还能加仓吗")
    assert q.asset_class == "cn_bond"
    assert "memo" in q.context_keys


def test_parse_query_detects_cn_equity_asset_class():
    q = parse_query("红利低波现在还值得定投吗")
    assert q.asset_class == "cn_equity"
    assert "memo" in q.context_keys


def test_parse_query_buy_timing_attaches_memo_without_instrument():
    q = parse_query("现在该不该买黄金")
    assert "memo" in q.context_keys


def test_parse_query_bullish_intent_still_attaches_memo():
    q = parse_query("518880 为什么看多？")
    assert "memo" in q.context_keys
    assert "scores" in q.context_keys


def test_parse_query_bearish_intent_attaches_memo():
    q = parse_query("159934 为什么看空？")
    assert q.intent == "bearish"
    assert "memo" in q.context_keys


def test_ask_command_returns_zero(tmp_path: Path):
    run_init(str(tmp_path), force=False)
    with patch("irc.queries.responder.call_chat", return_value=_resp("回答内容")):
        rc = run_ask(str(tmp_path), "黄金现在贵吗？")
    assert rc == 0


def test_ask_gold_question_passes_gold_context_to_llm(tmp_path: Path):
    """Regression: `irc ask "现在能入手黄金吗"` must pass gold memo + regime + band
    to the LLM so it can give a confident, data-grounded answer instead of
    refusing for lack of context.
    """
    from datetime import datetime, timezone, timedelta

    run_init(str(tmp_path), force=False)
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = tmp_path / "outputs" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "memo.md").write_text(
        "# 投资决策备忘录\n\n## 3. 黄金视角\n- regime=range_bound, zone=normal.\n",
        encoding="utf-8",
    )
    (out_dir / "scoring.json").write_text(
        '{"scores": [{"instrument": "518880", "score": 53.1}]}', encoding="utf-8",
    )
    (out_dir / "gold_regime.json").write_text(
        '{"regime": "range_bound", "tilt": "neutral", "zone": "normal"}', encoding="utf-8",
    )
    (out_dir / "gold_band.yaml").write_text(
        "high: 11.9\nlow: 7.4\nmidpoint: 9.6\n", encoding="utf-8",
    )
    (out_dir / "decision_report.md").write_text(
        "# Decision Report\n\n518880: blocked (blocked_no_proxy)\n", encoding="utf-8",
    )

    captured = {}

    def _capture_call_chat(**kwargs):
        captured["messages"] = kwargs.get("messages")
        return _resp("黄金 regime=range_bound，建议维持中性。")

    with patch("irc.queries.responder.call_chat", side_effect=_capture_call_chat):
        rc = run_ask(str(tmp_path), "现在能入手黄金吗")

    assert rc == 0
    user_msg = captured["messages"][-1]["content"]
    assert "黄金视角" in user_msg, "memo gold section must be in LLM context"
    assert "range_bound" in user_msg, "gold_regime must be in LLM context"
    assert "midpoint" in user_msg or "9.6" in user_msg, "gold_band must be in LLM context"
    assert "blocked_no_proxy" in user_msg, "decision_report must be in LLM context"
