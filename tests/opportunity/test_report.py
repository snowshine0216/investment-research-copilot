from __future__ import annotations

from irc.opportunity.cards import build_thesis_card
from irc.opportunity.discipline import PositionContext
from irc.opportunity.report import (
    compose_opportunity_report,
    compose_thesis_cards_yaml,
    compose_discipline_markdown,
)
from irc.opportunity.types import (
    DisciplineRow,
    LookthroughTarget,
    OpportunityRow,
)


def _row(state="core_dca", **overrides) -> OpportunityRow:
    base = dict(
        instrument_id="510300",
        name_cn="华泰柏瑞沪深300ETF",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state=state,
        opportunity_reason="核心宽基指数估值合理。",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def test_opportunity_report_summary_counts_states():
    rows = [
        _row(state="core_dca"), _row(state="core_dca", instrument_id="159919"),
        _row(state="pause_wait", instrument_id="512760"),
        _row(state="exclude", instrument_id="000001", thesis_state="falsified"),
    ]
    report = compose_opportunity_report(rows, date="2026-05-14")
    assert report["date"] == "2026-05-14"
    assert report["summary"]["core_dca_count"] == 2
    assert report["summary"]["pause_wait_count"] == 1
    assert report["summary"]["exclude_count"] == 1
    assert report["summary"]["small_watch_count"] == 0
    assert len(report["rows"]) == 4
    sample = report["rows"][0]
    for key in (
        "instrument_id", "name_cn", "asset_class", "theme",
        "lookthrough_target", "valuation_state", "heat_state",
        "thesis_state", "product_quality_state", "opportunity_state",
        "opportunity_reason", "evidence_gaps",
    ):
        assert key in sample


def test_thesis_cards_yaml_includes_required_fields():
    row = _row()
    pos = PositionContext(0.05, 0.0, 0.30, None, True)
    card = build_thesis_card(row, pos, "core_cn_equity", "宽基底仓。")
    payload = compose_thesis_cards_yaml([card])
    assert "instrument_id: '510300'" in payload or 'instrument_id: "510300"' in payload
    assert "do_not_sell_just_because:" in payload
    assert "drawdown_since_entry >= 0.20" in payload


def test_discipline_markdown_has_chinese_action_sections():
    """Spec integration test 3: Markdown has Chinese actionable sections."""
    rows = [
        DisciplineRow("510300", "宽基", "cn_etf", "broad", "core_dca",
                      "normal_dca", "none", "可定投"),
        DisciplineRow("512760", "半导体", "cn_etf", "semiconductor", "pause_wait",
                      "pause_dca", "review_required", "暂停加仓"),
        DisciplineRow("000001", "主动", "cn_equity_fund", "consumer", "exclude",
                      "do_not_buy", "exit_review", "退出复核"),
    ]
    md = compose_discipline_markdown(rows, date="2026-05-14")
    assert "## 今日可定投" in md
    assert "## 暂停加仓" in md
    assert "## 风险复核" in md
    assert "## 调仓复核" in md
    assert "## 退出复核" in md
    assert "## 关于回撤的说明" in md
    assert "20%" in md


def test_discipline_markdown_empty_categories_render_placeholder():
    md = compose_discipline_markdown([], date="2026-05-14")
    assert "## 今日可定投" in md
    assert "（无）" in md or "(none)" in md
