from __future__ import annotations
from irc.llm.cost_tracker import CostEntry, append_cost, redact_secret


def test_append_cost_returns_new_list_immutable():
    entries: list[CostEntry] = []
    e1 = CostEntry(
        task="news_summary", provider="deepseek", model="deepseek-chat",
        prompt_tokens=120, completion_tokens=80, latency_ms=540,
        ts="2026-05-07T15:00:00+08:00",
    )
    out = append_cost(entries, e1)
    assert len(out) == 1
    assert entries == []  # input unchanged


def test_redact_secret_keeps_last_4():
    assert redact_secret("sk-abcdef1234") == "sk-***1234"
    assert redact_secret("xyz") == "***"
    assert redact_secret("") == ""
