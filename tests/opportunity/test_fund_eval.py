from __future__ import annotations

import json

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis, ThesisEvidence
from irc.opportunity.fund_eval import (
    FundEval,
    evaluate_fund,
    render_fund_eval_json,
    render_fund_eval_md,
)
from irc.opportunity.types import OpportunityInput


def _intact_snapshot(fund_id: str) -> ActiveFundSnapshot:
    """A snapshot whose top holding carries a data + information leg so
    derive_thesis_from_evidence yields an intact thesis."""
    data_leg = ThesisEvidence(
        type="filing", source="filing", url="", date="2026-03-31",
        summary="600519 2025Q4 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    info_leg = ThesisEvidence(
        type="broker", source="broker", url="https://x", date="2026-04-01",
        summary="券商维持买入评级",
        scope="constituent", citation_kind="information",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=12.0,
        evidence=(data_leg, info_leg), failure_reasons=(),
        one_line_view="600519 贵州茅台",
    )
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-30",
        constituent_analyses=(c,), failure_reasons_by_symbol={},
    )


def _cheap_cold_input(iid: str) -> OpportunityInput:
    """cheap valuation (low percentile) + cold heat + theme so thesis can be intact."""
    return OpportunityInput(
        instrument_id=iid, asset_class="cn_equity_fund", market="cn_off_exchange",
        theme="holdings_sector", name_cn="算力金属基金", role="satellite_cn_metals",
        valuation_percentile_self=0.10,            # cheap (< 0.20)
        ret_1m=-0.05, ret_3m=-0.08,                # cold heat (>= 2 signals)
        manager_tenure_years=6.0, aum_stability_pct=90.0,
        expense_ratio=0.005, aum_cny=5_000_000_000.0,  # acceptable/strong product
    )


def test_evaluate_fund_core_dca_when_cheap_cold_intact_acceptable():
    inp = _cheap_cold_input("980001")
    snap = _intact_snapshot("980001")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert isinstance(ev, FundEval)
    assert ev.opportunity_state == "core_dca"
    assert ev.core_dca is True
    assert ev.dca_action in ("normal_dca", "accelerate_dca")
    assert ev.valuation_state == "cheap"
    assert ev.role == "satellite_cn_metals"
    # top_holdings derived from constituent_analyses
    assert ev.top_holdings == (("600519", "贵州茅台", 12.0),)


def test_evaluate_fund_expensive_is_pause_wait_not_core():
    inp = _cheap_cold_input("980002")
    inp = type(inp)(**{**inp.__dict__, "valuation_percentile_self": 0.95})  # very_expensive
    snap = _intact_snapshot("980002")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert ev.opportunity_state == "pause_wait"
    assert ev.core_dca is False


def test_evaluate_fund_snapshot_none_surfaces_missing_constituent_gap():
    inp = _cheap_cold_input("980003")
    ev = evaluate_fund(inp, None, role="satellite_cn_metals")
    assert ev.core_dca is False
    assert "missing_constituent_snapshot" in ev.evidence_gaps


def test_evaluate_fund_insufficient_inputs_yields_insufficient_substates():
    inp = OpportunityInput(
        instrument_id="980004", asset_class="cn_equity_fund",
        market="cn_off_exchange", theme="holdings_sector", name_cn="无数据基金",
        role="satellite_cn_metals",
    )  # no valuation, no returns, no product metadata
    ev = evaluate_fund(inp, None, role="satellite_cn_metals")
    assert ev.valuation_state == "evidence_insufficient"
    assert ev.heat_state == "evidence_insufficient"
    assert ev.core_dca is False


def _two_evals():
    a = FundEval(
        instrument_id="980001", name_cn="算力金属A",
        valuation_state="cheap", heat_state="cold", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        dca_action="normal_dca", core_dca=True, note_cn="估值便宜……",
        top_holdings=(("600519", "贵州茅台", 12.0),),
        evidence_gaps=(), role="satellite_cn_metals",
    )
    b = FundEval(
        instrument_id="980002", name_cn="算力金属B",
        valuation_state="very_expensive", heat_state="crowded",
        thesis_state="intact", product_quality_state="acceptable",
        opportunity_state="pause_wait", dca_action="pause_dca", core_dca=False,
        note_cn="估值或热度高……", top_holdings=(), evidence_gaps=(),
        role="satellite_cn_metals",
    )
    return (a, b)


def test_render_md_lists_core_dca_headline_and_one_row_per_fund():
    md = render_fund_eval_md(_two_evals())
    assert "980001" in md and "980002" in md           # one row per fund
    assert "core_dca" in md                              # the core_dca headline list
    assert "算力金属A" in md
    # the core_dca fund is named in the headline section
    assert md.count("980001") >= 1


def test_render_json_round_trips_fundeval_fields():
    payload = render_fund_eval_json(_two_evals())
    doc = json.loads(payload)
    assert isinstance(doc["funds"], list)
    first = next(f for f in doc["funds"] if f["instrument_id"] == "980001")
    assert first["opportunity_state"] == "core_dca"
    assert first["core_dca"] is True
    assert first["dca_action"] == "normal_dca"
    assert first["top_holdings"] == [["600519", "贵州茅台", 12.0]]
    assert first["role"] == "satellite_cn_metals"


# ── Item 002 (todos-critical-fixes 2026-07-03): dual-leg gate on the eval surface ──

def _data_only_snapshot(fund_id: str) -> ActiveFundSnapshot:
    """Filing-only (data-leg-only) constituent evidence, fund_level_evidence=()."""
    data_leg = ThesisEvidence(
        type="filing", source="filing", url="", date="2026-03-31",
        summary="600519 2025Q4 财报已披露（口径未核实）",
        scope="constituent", citation_kind="data",
        owner_instrument_id=fund_id, parent_fund_id=fund_id, constituent_key="600519",
    )
    c = ConstituentAnalysis(
        symbol="600519", name_cn="贵州茅台", weight_pct=12.0,
        evidence=(data_leg,), failure_reasons=(),
        one_line_view="600519 贵州茅台",
    )
    return ActiveFundSnapshot(
        fund_id=fund_id, source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-30",
        constituent_analyses=(c,), failure_reasons_by_symbol={},
    )


def test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca():
    """AC9: cheap + cold + acceptable + DATA-ONLY evidence must not compose to
    core_dca — the false-confidence bug this item fixes (TODOS.md line ~51)."""
    inp = _cheap_cold_input("980005")
    snap = _data_only_snapshot("980005")
    ev = evaluate_fund(inp, snap, role="satellite_cn_metals")
    assert ev.thesis_state == "evidence_insufficient"
    assert ev.opportunity_state == "small_watch"
    assert ev.core_dca is False
