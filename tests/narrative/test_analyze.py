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


from irc.fundamentals.types import FundLevelSnapshot, FundNavReport  # noqa: E402
from irc.opportunity.types import OpportunityInput  # noqa: E402


def _inp(iid: str, asset_class: str, *, tracked_index=None, theme=None) -> OpportunityInput:
    return OpportunityInput(
        instrument_id=iid, asset_class=asset_class, market="cn_off_exchange",
        theme=theme, tracked_index=tracked_index, name_cn=f"fund-{iid}", role="r",
        is_holding=False, portfolio_weight=None, target_band_low=None,
        target_band_high=None, venue_compatible=True,
    )


def _fund_level_snap(iid: str) -> FundLevelSnapshot:
    return FundLevelSnapshot(
        fund_id=iid, nav_report=FundNavReport(
            fund_id=iid, fund_name=iid, latest_nav=4.5, latest_nav_date="2026-03-15",
            nav_history=(("2026-03-15", 4.5),), source_report_quarter="2026Q1"),
        announcements=(), evidence=(_evidence(iid),),
        source_report_quarter="2026Q1", cache_probed_at="2026-06-02",
    )


def test_analyze_fund_wires_cache_and_builder(monkeypatch) -> None:
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _inp("000A", "cn_equity_fund"))
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000A"))
    rpt = A.analyze_fund(
        _shortlist_row("000A"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"),
        role="satellite_cn_metals",
    )
    assert rpt.thesis_evidence[0].citation_id == _evidence("000A").citation_id


def test_load_snapshot_for_row_dispatches_active(monkeypatch) -> None:
    calls = {"active": 0, "nav": 0}
    monkeypatch.setattr(A, "load_active_fund_cache",
                        lambda iid, q, root: calls.__setitem__("active", calls["active"] + 1))
    monkeypatch.setattr(A, "_load_latest_nav_cached",
                        lambda iid, root: calls.__setitem__("nav", calls["nav"] + 1))
    inp = _inp("000A", "cn_equity_fund")
    A._load_snapshot_for_row(inp, quarter="2026Q1",
                             data_dir=__import__("pathlib").Path("/tmp"))
    assert calls == {"active": 1, "nav": 0}  # AC5/AC14 — active loader only


def test_load_snapshot_for_row_dispatches_fund_level(monkeypatch) -> None:
    calls = {"active": 0, "nav": 0}
    monkeypatch.setattr(A, "load_active_fund_cache",
                        lambda iid, q, root: calls.__setitem__("active", calls["active"] + 1))
    monkeypatch.setattr(A, "_load_latest_nav_cached",
                        lambda iid, root: (calls.__setitem__("nav", calls["nav"] + 1),
                                           _fund_level_snap("000B"))[1])
    inp = _inp("000B", "cn_etf", tracked_index="csi300")
    snap = A._load_snapshot_for_row(inp, quarter="2026Q1",
                                    data_dir=__import__("pathlib").Path("/tmp"))
    assert calls == {"active": 0, "nav": 1}  # fund-level loader only
    assert isinstance(snap, FundLevelSnapshot)


def test_load_snapshot_for_row_returns_none_when_no_provider_symbol(monkeypatch) -> None:
    """FIX 4: silent-miss branch — when the resolved target has no provider_symbol,
    _load_snapshot_for_row must return None without calling any cache loader."""
    active_calls: list = []
    nav_calls: list = []
    monkeypatch.setattr(A, "load_active_fund_cache",
                        lambda iid, q, root: active_calls.append(iid))
    monkeypatch.setattr(A, "_load_latest_nav_cached",
                        lambda iid, root: nav_calls.append(iid))
    # A bare cn_etf with no tracked_index/theme routes to broad_index "unknown"
    # with no provider_symbol — the silent-miss branch.
    inp = _inp("000Z", "cn_etf")
    result = A._load_snapshot_for_row(inp, quarter="2026Q1",
                                      data_dir=__import__("pathlib").Path("/tmp"))
    assert result is None
    assert active_calls == []
    assert nav_calls == []


def test_analyze_fund_fund_level_issues_no_build(monkeypatch) -> None:
    """AC4 — analyze_fund reads only; never invokes build_snapshot."""
    import irc.fundamentals.snapshot as S

    def _no_build(*a, **k):
        raise AssertionError("analyze_fund must not build")

    monkeypatch.setattr(S, "build_snapshot", _no_build)
    monkeypatch.setattr(A, "load_active_fund_cache", lambda iid, q, root: None)
    monkeypatch.setattr(A, "_load_latest_nav_cached", lambda iid, root: _fund_level_snap("000B"))
    monkeypatch.setattr(A, "_build_input", lambda *a, **k: _inp("000B", "cn_etf",
                                                                tracked_index="csi300"))
    monkeypatch.setattr(A, "build_opportunity_row",
                        lambda inp, tt, *, snapshot, theme_report: _row("000B"))
    rpt = A.analyze_fund(
        _shortlist_row("000B"), instr=None, con=object(), provider=object(),
        quarter="2026Q1", data_dir=__import__("pathlib").Path("/tmp"), role="r",
    )
    assert rpt.instrument_id == "000B"
