from __future__ import annotations

import dataclasses

import pytest

from irc.narrative.schemas import (
    BasketStock,
    Holding,
    NarrativeBasket,
    NarrativeFundReport,
    OverlapResult,
    ShortlistRow,
)


def test_basket_stock_is_frozen() -> None:
    s = BasketStock(symbol="601899", name_cn="紫金矿业", metal="copper_gold")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.symbol = "000001"  # type: ignore[misc]


def test_narrative_basket_holds_stocks_and_thresholds() -> None:
    b = NarrativeBasket(
        narrative_id="compute_metals",
        display_name_cn="算力金属",
        display_name_en="Compute-demand metals",
        thesis_cn="AI 数据中心拉动铜铝锡需求",
        basket=(BasketStock(symbol="601899", name_cn="紫金矿业", metal="copper_gold"),),
        industries_sw=("有色金属/工业金属",),
        min_basket_weight_pct=15.0,
        min_overlap_count=2,
        top_n=15,
    )
    assert b.narrative_id == "compute_metals"
    assert b.basket[0].symbol == "601899"
    assert b.min_overlap_count == 2


def test_holding_and_overlap_and_shortlist_construct() -> None:
    h = Holding(symbol="601899", name_cn="紫金矿业", weight_pct=8.0, sw_industry="有色金属/工业金属")
    ov = OverlapResult(
        basket_weight_pct=8.0,
        overlap_count=1,
        matched_symbols=("601899",),
        industry_credit_symbols=(),
    )
    row = ShortlistRow(
        instrument_id="000123",
        name_cn="某有色基金",
        asset_class="cn_equity_fund",
        overlap=ov,
        holdings=(h,),
    )
    assert row.overlap.basket_weight_pct == 8.0
    assert row.holdings[0].weight_pct == 8.0


def test_narrative_fund_report_construct() -> None:
    rpt = NarrativeFundReport(
        instrument_id="000123",
        name_cn="某有色基金",
        position_risk_level="elevated",
        risk_rationale="elevated — very_expensive valuation",
        risk_drivers=("valuation_state",),
        valuation_state="very_expensive",
        heat_state="overheated",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="small_watch",
        dca_action="slow_dca",
        risk_action="trim_review",
        falsification_triggers=("theme thesis moves to falsified",),
        trim_triggers=("valuation_state in [expensive, very_expensive]",),
        review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
        thesis_evidence=(),
    )
    assert rpt.position_risk_level == "elevated"
    assert rpt.risk_drivers == ("valuation_state",)
    assert rpt.opportunity_state == "small_watch"
    assert rpt.risk_action == "trim_review"
    assert rpt.thesis_evidence == ()
