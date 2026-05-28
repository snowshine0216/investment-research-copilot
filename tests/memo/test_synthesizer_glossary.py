from __future__ import annotations

from unittest.mock import patch

from irc.memo.synthesizer import synthesize_memo


def _capture_user_prompt() -> str:
    captured: dict[str, object] = {}

    def fake_call_chat(route, messages, **kwargs):
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
    # F6: old phrase `不得直接引用为业绩依据` replaced by the F6 guardrail
    # clause; assert the new equivalent contract is present.
    assert "财报已披露（口径未核实）" in user_msg
    assert "禁止在任何段落输出" in user_msg
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


def test_synthesize_memo_prompt_forbids_multi_instrument_uncited_summary() -> None:
    """Rule 8 (2026-05-25): the LLM was generating multi-ETF summary
    paragraphs like '证据池中五只黄金 ETF（518880、…）状态均为...' with no
    [ref:...] markers, triggering 5× uncited_conclusion findings. The
    prompt must explicitly forbid this pattern and require per-instrument
    bullets with per-instrument citations."""
    user_msg = _capture_user_prompt()
    assert "每只一行 bullet" in user_msg
    assert "证据池中 N 只 X" in user_msg or "无 [ref:...] 标记" in user_msg
    # Concrete example must be present so the LLM has a template to copy.
    assert "518880" in user_msg
    assert "159937" in user_msg


def test_synthesize_memo_prompt_lists_canonical_tldr_phrasings() -> None:
    """Rule 9 (2026-05-25): TL;DR portfolio-level statements containing
    action keywords (暂停加仓 / 减速定投) must use one of the audit-whitelist
    phrasings. The prompt must list them verbatim so the LLM has a fixed
    vocabulary instead of inventing novel paraphrases."""
    user_msg = _capture_user_prompt()
    assert "本期黄金 ETF 全部暂停加仓" in user_msg
    assert "所有可执行标的均为条件性减速定投" in user_msg
    # The forbidden-paraphrase list closes the gap that caused the
    # 2026-05-25 halt cycle.
    assert "暂不主动加仓" in user_msg or "本期无主动加仓信号" in user_msg


def test_synthesize_memo_prompt_requires_refs_on_any_instrument_id_mention() -> None:
    """Rule 10 (2026-05-25): the per-instrument [ref:...] requirement of
    Rule 6 must apply to ANY paragraph mentioning a fund/ETF code, not
    just to conclusion paragraphs. Description-style prose ('状态分布',
    '估值分桶') must also carry the [ref:...] marker."""
    user_msg = _capture_user_prompt()
    assert "提及具体基金代码" in user_msg
    assert "描述性" in user_msg
    assert "状态分布" in user_msg or "估值分桶" in user_msg


def test_synthesize_memo_prompt_forbids_cross_fund_citation_borrow() -> None:
    """Rule 11 (2026-05-25): a constituent held by ≥2 funds gets a
    distinct [ref:...] under each fund's evidence pool. The LLM was
    grabbing the wrong fund's [ref:...] when writing a 'supplementary
    disclosure' paragraph for a specific fund — that triggers
    `wrong_instrument_citation`. The prompt must forbid the
    supplementary-disclosure pattern and require same-owner [ref:...]
    when constituents are mentioned."""
    user_msg = _capture_user_prompt()
    assert "补充披露" in user_msg
    assert "owner_instrument_id" in user_msg
    assert "wrong_instrument_citation" in user_msg or "cross-borrow" in user_msg


def test_synthesizer_prompt_locks_qdii_premium_marker_block() -> None:
    """Item 003 constraint: when the skeleton contains
    IRC_QDII_PREMIUM_BEGIN, the synthesizer must be instructed to preserve
    the block verbatim (7th verbatim-lock clause)."""
    from unittest.mock import patch
    from irc.memo.synthesizer import synthesize_memo

    captured_messages: list = []

    def _fake_call_chat(route, messages, **kwargs):
        captured_messages.append(messages)

        class _Resp:
            text = "ok"
            prompt_tokens = 0
            completion_tokens = 0
        return _Resp()

    skeleton = (
        "## 6. 风险提示\n"
        "<!-- IRC_QDII_PREMIUM_BEGIN -->\n"
        "溢价/折价：QDII 候选标的二级市场偏离快照（数据截止 2026-05-26，阈值 5%）：\n"
        " - 159501 标普消费ETF：+6.92%（超阈值，已暂缓执行）\n"
        "<!-- IRC_QDII_PREMIUM_END -->\n"
    )
    with patch("irc.memo.synthesizer.call_chat", side_effect=_fake_call_chat):
        synthesize_memo(skeleton, raw_ref_pool=[], route=None)  # type: ignore[arg-type]
    user_msg = next(m for m in captured_messages[0] if m["role"] == "user")["content"]
    assert "IRC_QDII_PREMIUM_BEGIN/END" in user_msg
    assert "原样保留" in user_msg
