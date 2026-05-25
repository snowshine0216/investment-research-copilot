from __future__ import annotations

from unittest.mock import patch

from irc.memo.synthesizer import synthesize_memo


def _capture_user_prompt() -> str:
    captured: dict[str, object] = {}

    def fake_call_chat(route, messages, temperature):
        captured["messages"] = messages

        class _R:
            text = "stub"
            prompt_tokens = 0
            completion_tokens = 0
        return _R()

    with patch("irc.memo.synthesizer.call_chat", side_effect=fake_call_chat):
        synthesize_memo(skeleton="# stub", raw_ref_pool=["ref-1"], route=None)  # type: ignore[arg-type]

    msgs = captured["messages"]
    return next(m for m in msgs if m["role"] == "user")["content"]


def test_synthesize_memo_user_prompt_includes_cost_grade_glossary() -> None:
    """The synthesizer must prime the LLM with a glossary that distinguishes
    the price-percentile bucket (carried in 状态=A/B/C/D) from the cost_grade
    factor score. Without this glossary the LLM collapses both into one
    "valuation" axis — exactly the 2026-05-18 audit finding on 000105
    ("estimated cheap" narrative vs cost_grade=85). The check below makes
    sure future prompt edits don't silently drop the disambiguation.
    """
    user_msg = _capture_user_prompt()
    assert "cost_grade" in user_msg
    assert "字段说明" in user_msg
    # The glossary must explicitly call out that cost_grade and 状态's
    # valuation bucket are independent — that's the load-bearing claim.
    assert "独立" in user_msg or "不等于" in user_msg


def test_synthesize_memo_prompt_forbids_directional_price_prediction() -> None:
    """Audit P2 (2026-05-20) — '对金价短期不利' was an unsupported directional
    prediction. The prompt must explicitly prohibit forward-price guidance."""
    user_msg = _capture_user_prompt()
    assert "方向性预测" in user_msg
    assert "禁止" in user_msg


def test_synthesize_memo_prompt_requires_explicit_data_gap_callout() -> None:
    """Audit P3 (2026-05-20) — when valuation percentile data is missing,
    the synthesizer must declare the gap, not fabricate '中位附近' / '偏高位置'."""
    user_msg = _capture_user_prompt()
    assert "数据缺失" in user_msg
    # Must require disclosure rather than fabrication:
    assert "声明" in user_msg or "披露" in user_msg or "标注" in user_msg


def test_synthesize_memo_prompt_forbids_qdii_premium_conclusion_without_data() -> None:
    """Audit P6 (2026-05-20) — '敞口可接受' was emitted in §4 while §6 said
    QDII premium/discount data was not collected. Prompt must explicitly
    forbid that conclusion when the data is absent."""
    user_msg = _capture_user_prompt()
    assert "QDII" in user_msg
    assert "溢价" in user_msg or "折价" in user_msg
    # Must forbid the specific conclusion, not just warn:
    assert "敞口可接受" in user_msg
    assert "禁止" in user_msg


def test_synthesize_memo_prompt_balances_positive_logic_with_negative_signals() -> None:
    """Audit 2026-05-24 — positive bottom-up evidence must be paired with
    valuation/heat/product-quality negatives, and raw revenue_yoy decimals
    must not be copied as ambiguous prose."""
    user_msg = _capture_user_prompt()
    assert "正面逻辑" in user_msg
    assert "very_expensive" in user_msg
    assert "overheated" in user_msg
    assert "weak" in user_msg
    assert "revenue_yoy" in user_msg
    assert "不得直接引用为业绩依据" in user_msg
    assert "必须换算为百分比" not in user_msg


def test_synthesize_memo_prompt_treats_target_weight_as_cap() -> None:
    user_msg = _capture_user_prompt()
    assert "权重上限" in user_msg
    assert "非强制建仓目标" in user_msg
    assert "触发条件未满足时实际执行量为零" in user_msg


def test_synthesize_memo_prompt_requires_refs_on_instrument_conclusions() -> None:
    user_msg = _capture_user_prompt()
    assert "[ref:" in user_msg
    assert "具体标的" in user_msg
    assert "同一段" in user_msg or "同一行" in user_msg
