from __future__ import annotations

from irc.commands.memo_cmd import _MACRO_SUMMARY, _compose_risk_notes


def test_macro_summary_discloses_incomplete_a_share_valuation_collection() -> None:
    assert "采集不完整" in _MACRO_SUMMARY
    assert "以证据池中的具体读数为准" not in _MACRO_SUMMARY


def test_risk_notes_use_conditional_real_yield_language() -> None:
    notes = "\n".join(_compose_risk_notes("2026-05-22"))
    assert "实际利率反弹会压制金价" not in notes
    assert "通常对金价形成压制" in notes
    assert "本期实际利率数据缺失" in notes
