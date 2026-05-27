"""End-to-end tests for the `top_holdings_broker_thin` advisory gap.

Covers AC1 (gap code in advisory_gaps), AC2 (emitted by derive_thesis_from_evidence),
AC3 (threshold), AC4 (active-fund only), AC6 (H3 predicate unchanged).
"""
from __future__ import annotations

from irc.fundamentals.types import (
    ActiveFundSnapshot,
    ConstituentAnalysis,
    FundLevelSnapshot,
)


def _analysis(symbol: str, weight: float, failures: tuple[str, ...] = ()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight,
        evidence=(), failure_reasons=failures, one_line_view="",
    )


def _active_snap(*analyses: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )


def test_active_fund_with_2_broker_empty_in_top5_emits_advisory_gap():
    """AC1+AC3: count_broker_empty_top5 >= 2 triggers the gap."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" in gaps


def test_active_fund_with_25pct_single_holding_broker_empty_emits_gap():
    """AC3: weight_broker_empty_top5 >= 20.0 alone is sufficient."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 25.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" in gaps


def test_active_fund_below_threshold_no_gap():
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = _active_snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="cn_equity_fund", owner_instrument_id="005827",
    )
    assert "top_holdings_broker_thin" not in gaps


def test_fund_level_snapshot_never_emits_advisory_gap():
    """AC4: FundLevelSnapshot (passive ETF / gold / bond / QDII) is exempt."""
    from irc.opportunity.thesis_evidence import derive_thesis_from_evidence
    snap = FundLevelSnapshot(
        fund_id="518880", source_report_quarter="2026Q1",
        cache_probed_at="", nav_report=None, announcements=(),
        evidence=(), evidence_gaps=(),
    )
    _, _, _, gaps, _ = derive_thesis_from_evidence(
        snap, None, asset_class="gold", owner_instrument_id="518880",
    )
    assert "top_holdings_broker_thin" not in gaps


def test_active_fund_advisory_gap_goes_to_advisory_gaps_not_evidence_gaps():
    """AC6: H3 partition predicate is preserved — gap routes through advisory_gaps,
    NOT evidence_gaps. Row stays publishable."""
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert "top_holdings_broker_thin" in row.advisory_gaps
    assert "top_holdings_broker_thin" not in row.evidence_gaps
    # H3 publishability predicate stays exactly `evidence_gaps == ()`.
    # Other unrelated structural gaps may still be present (e.g.
    # missing_valuation_data) — the assertion that matters is the advisory
    # gap does NOT leak into evidence_gaps.


def test_row_to_dict_serializes_advisory_gaps():
    from irc.opportunity.report import _row_to_dict
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    d = _row_to_dict(row)
    assert d["advisory_gaps"] == ["top_holdings_broker_thin"]


def test_card_to_dict_serializes_advisory_gaps():
    from irc.opportunity.cards import build_thesis_card
    from irc.opportunity.discipline import PositionContext
    from irc.opportunity.report import _card_to_dict
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput
    snap = _active_snap(
        _analysis("A", 8.0, ("broker_empty:A",)),
        _analysis("B", 7.0, ("broker_empty:B",)),
        _analysis("C", 6.0, ()),
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    pos = PositionContext(is_holding=False, drawdown_since_entry=None,
                         portfolio_weight=None, target_band_low=None,
                         target_band_high=None)
    card = build_thesis_card(row, pos, role="", entry_reason="")
    d = _card_to_dict(card)
    assert d["advisory_gaps"] == ["top_holdings_broker_thin"]


def test_discipline_section_header_appends_advisory_gap_suffix():
    """AC9: the `## 今日可定投` per-fund line gains a 证据缺口 suffix when the
    row carries top_holdings_broker_thin. Append-only — does not perturb
    existing column positions.
    """
    from irc.opportunity.report import _render_section
    from irc.opportunity.types import DisciplineRow
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="small_watch", dca_action="slow_dca",
        risk_action="none", note_cn="证据偏薄",
        advisory_gaps=("top_holdings_broker_thin",),
    )
    rendered = _render_section("今日可定投", [drow])
    assert "证据缺口：核心持仓券商覆盖不足" in rendered
    # Suffix appears AFTER asset state markers but BEFORE note_cn.
    assert rendered.index("证据缺口：核心持仓券商覆盖不足") < rendered.index("证据偏薄")


def test_discipline_section_header_no_suffix_when_advisory_gaps_empty():
    from irc.opportunity.report import _render_section
    from irc.opportunity.types import DisciplineRow
    drow = DisciplineRow(
        instrument_id="005827", name_cn="易方达蓝筹精选",
        asset_class="cn_equity_fund", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="买入候选",
    )
    rendered = _render_section("今日可定投", [drow])
    assert "证据缺口" not in rendered
