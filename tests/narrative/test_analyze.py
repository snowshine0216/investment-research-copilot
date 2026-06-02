from __future__ import annotations

from irc.fundamentals.types import ConstituentAnalysis, LookthroughTarget, ThesisEvidence
from irc.narrative import analyze as A
from irc.narrative.schemas import Holding, OverlapResult, ShortlistRow
from irc.opportunity.types import OpportunityRow


def _evidence(iid: str) -> ThesisEvidence:
    return ThesisEvidence(
        type="filing", source="cninfo", url="", date="2026-03-31",
        summary=f"{iid} 2026Q1 财报已披露（口径未核实）",
        scope="instrument", citation_kind="data",
        owner_instrument_id=iid, parent_fund_id=None, constituent_key=None,
    )


def _row(iid: str, *, valuation: str = "very_expensive",
         gaps: tuple[str, ...] = ()) -> OpportunityRow:
    return OpportunityRow(
        instrument_id=iid, name_cn=f"fund-{iid}", asset_class="cn_equity_fund",
        theme="metals",
        lookthrough_target=LookthroughTarget(kind="active_fund", key=iid, display_cn=f"fund-{iid}"),
        valuation_state=valuation, heat_state="overheated", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="small_watch",
        opportunity_reason="估值偏高但逻辑完整", evidence_gaps=gaps,
        thesis_evidence=(_evidence(iid),),
        constituent_analyses=(
            ConstituentAnalysis(symbol="601899", name_cn="紫金矿业", weight_pct=38.0,
                                evidence=(), failure_reasons=(), one_line_view="x"),
        ),
    )


def _shortlist_row(iid: str) -> ShortlistRow:
    ov = OverlapResult(basket_weight_pct=22.0, overlap_count=3,
                       matched_symbols=(), industry_credit_symbols=())
    return ShortlistRow(instrument_id=iid, name_cn=f"fund-{iid}",
                        asset_class="cn_equity_fund", overlap=ov,
                        holdings=(Holding(symbol="601899", name_cn="紫金矿业", weight_pct=38.0),))


def test_risk_view_reads_real_row_states() -> None:
    view = A._risk_view_from_row(_row("000A"), _shortlist_row("000A"))
    assert view.valuation_state == "very_expensive"
    assert view.heat_state == "overheated"
    assert view.evidence_gaps == ()
    assert view.top_holdings[0] == ("601899", "紫金矿业", 38.0)  # from constituent_analyses


def test_risk_view_falls_back_to_screen_holdings_when_no_constituents() -> None:
    row = _row("000A")
    row = OpportunityRow(**{**row.__dict__, "constituent_analyses": ()})
    view = A._risk_view_from_row(row, _shortlist_row("000A"))
    assert view.top_holdings[0] == ("601899", "紫金矿业", 38.0)  # from screen Holding


def test_report_from_card_carries_evidence_and_states() -> None:
    rpt = A._report_from_card(_row("000A"), _shortlist_row("000A"),
                              role="satellite_cn_metals")
    assert rpt.position_risk_level in ("elevated", "high")
    assert "valuation_state" in rpt.risk_drivers
    assert rpt.opportunity_state == "small_watch"
    # is_holding=False so trim_review doesn't fire for valuation/heat alone;
    # derive_risk_action returns "none" for a prospective (non-held) position.
    assert rpt.risk_action in ("none", "trim_review", "review_required")
    assert rpt.thesis_evidence and rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id
    assert rpt.review_cadence == "weekly_light_monthly_full"


def test_report_from_card_missing_snapshot_is_insufficient() -> None:
    row = _row("000A", valuation="evidence_insufficient",
               gaps=("missing_constituent_snapshot",))
    rpt = A._report_from_card(row, _shortlist_row("000A"), role="r")
    assert rpt.position_risk_level == "insufficient"
    assert "evidence_gaps" in rpt.risk_drivers


def test_analyze_fund_wires_cache_and_builder(monkeypatch) -> None:
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: object())
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000A"))
    rpt = A.analyze_fund(
        _shortlist_row("000A"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"),
        role="satellite_cn_metals",
    )
    assert rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id
