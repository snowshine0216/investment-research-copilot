from __future__ import annotations

from irc.memo.picks_table import PickRow, render_picks_table


def test_render_picks_table_dedupes_and_lists_action_and_rationale():
    rows = [
        PickRow(
            instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
            role="core_gold_hedge", target_weight=0.564, composite_score=51.8,
            opportunity_state="core_dca", dca_action="normal_dca", risk_action="none",
            one_line_reason="估值百分位 18% 偏低；近期回报 -3% 热度可控；产品费率 0.5% 合规",
        ),
        PickRow(
            instrument_id="006075", name_cn="易方达标普500", asset_class="us_etf",
            role="core_us_equity", target_weight=0.161, composite_score=52.4,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="估值百分位 78% 偏高；放慢定投",
        ),
        # Duplicate of 006075 — must be dropped
        PickRow(
            instrument_id="006075", name_cn="易方达标普500", asset_class="us_etf",
            role="core_us_equity", target_weight=0.161, composite_score=52.4,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="重复",
        ),
    ]
    md = render_picks_table(rows)
    assert "518880" in md and "华安黄金ETF" in md
    assert md.count("006075") == 1, "duplicate instrument_id must be deduped"
    # Header columns
    for col in ("代码", "名称", "角色", "目标权重", "状态", "本期行动", "主要理由"):
        assert col in md
    # Action labels expanded into Chinese
    assert "正常定投" in md  # normal_dca
    assert "减速定投" in md  # slow_dca
    # Target weights formatted as percentages, 1 decimal
    assert "56.4%" in md
    assert "16.1%" in md


def test_render_picks_table_appends_scoring_methodology_footnote():
    """Audit P5 (2026-05-20) — 综合分 is used to order picks but the memo
    never discloses methodology. Footnote must reference multi-factor
    derivation and include the explicit '不构成投资建议' disclaimer."""
    rows = [
        PickRow(
            instrument_id="518880", name_cn="华安黄金ETF", asset_class="gold",
            role="core_gold_hedge", target_weight=0.564, composite_score=51.8,
            opportunity_state="core_dca", dca_action="normal_dca", risk_action="none",
            one_line_reason="reason",
        ),
    ]
    md = render_picks_table(rows)
    assert "综合分" in md
    # Footnote present (the load-bearing disclaimer phrase from the audit):
    assert "不构成投资建议" in md
    # Mention factor composition so the score isn't a black box:
    assert ("估值" in md and "热度" in md) or "多因子" in md


def test_render_picks_table_footnote_only_once_even_with_many_rows():
    """Two rows in, one footnote out — footnote must not be duplicated per row."""
    rows = [
        PickRow(
            instrument_id="A", name_cn="一", asset_class="x", role="r",
            target_weight=0.1, composite_score=10.0, opportunity_state="core_dca",
            dca_action="normal_dca", risk_action="none", one_line_reason="x",
        ),
        PickRow(
            instrument_id="B", name_cn="二", asset_class="x", role="r",
            target_weight=0.1, composite_score=10.0, opportunity_state="core_dca",
            dca_action="normal_dca", risk_action="none", one_line_reason="x",
        ),
    ]
    md = render_picks_table(rows)
    assert md.count("不构成投资建议") == 1


def test_render_picks_table_footnote_emitted_even_when_no_rows():
    """Empty picks table still gets the disclaimer — methodology disclosure
    is decoupled from row count."""
    md = render_picks_table([])
    assert "不构成投资建议" in md


def test_render_picks_table_groups_zero_weight_as_observation_only():
    rows = [
        PickRow(
            instrument_id="510050", name_cn="上证50ETF", asset_class="cn_etf",
            role="core_cn_equity", target_weight=0.0, composite_score=59.9,
            opportunity_state="small_watch", dca_action="slow_dca", risk_action="none",
            one_line_reason="渠道不可购买，仅观察",
        ),
    ]
    md = render_picks_table(rows)
    assert "仅观察" in md
    assert "0.0%" in md or "观察" in md
