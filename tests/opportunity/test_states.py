from __future__ import annotations
import pytest

from irc.opportunity.states import classify_valuation
from irc.opportunity.types import OpportunityInput


def _make(**kwargs) -> OpportunityInput:
    base = {"instrument_id": "X", "asset_class": "cn_etf", "market": "cn_on_exchange"}
    base.update(kwargs)
    return OpportunityInput(**base)


def test_valuation_evidence_insufficient_when_no_data():
    state, reason = classify_valuation(_make())
    assert state == "evidence_insufficient"
    assert "valuation" in reason.lower() or "估值" in reason


def test_valuation_cheap_when_self_percentile_below_20():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.15))
    assert state == "cheap"


def test_valuation_reasonable_low_when_self_percentile_20_to_40():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.30))
    assert state == "reasonable_low"


def test_valuation_fair_when_self_percentile_40_to_70():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.55))
    assert state == "fair"


def test_valuation_expensive_when_self_percentile_70_to_90():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.80))
    assert state == "expensive"


def test_valuation_very_expensive_when_self_percentile_above_90():
    state, _ = classify_valuation(_make(valuation_percentile_self=0.95))
    assert state == "very_expensive"


def test_valuation_uses_vs_benchmark_when_self_history_missing():
    state, _ = classify_valuation(_make(
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=0.10,
    ))
    assert state == "cheap"


def test_valuation_never_infers_cheapness_from_drawdown_alone():
    state, _ = classify_valuation(_make(drawdown_since_entry=0.30))
    assert state == "evidence_insufficient"


from irc.opportunity.states import classify_heat


def test_heat_insufficient_when_no_data():
    state, _ = classify_heat(_make())
    assert state == "evidence_insufficient"


def test_heat_cold_when_returns_negative_and_no_crowding():
    state, _ = classify_heat(_make(
        ret_3m=-0.05, ret_6m=-0.10, ret_12m=-0.15,
        premium_discount_pct=-0.005,
    ))
    assert state == "cold"


def test_heat_normal_when_mixed_returns():
    state, _ = classify_heat(_make(
        ret_3m=0.02, ret_6m=0.05, ret_12m=0.08,
        premium_discount_pct=0.0,
    ))
    assert state == "normal"


def test_heat_crowded_when_recent_returns_high():
    state, _ = classify_heat(_make(
        ret_1m=0.10, ret_3m=0.25, ret_6m=0.35,
        premium_discount_pct=0.01,
    ))
    assert state == "crowded"


def test_heat_overheated_when_extreme_returns_or_premium():
    state, _ = classify_heat(_make(
        ret_3m=0.40, ret_6m=0.55,
        premium_discount_pct=0.03,
    ))
    assert state == "overheated"


def test_strong_recent_returns_do_not_lower_heat():
    """Recent strong returns should INCREASE heat risk, not decrease it."""
    state, _ = classify_heat(_make(
        ret_1m=0.15, ret_3m=0.30,
        premium_discount_pct=0.025,
    ))
    assert state in ("crowded", "overheated")


from irc.opportunity.states import classify_thesis


def test_thesis_insufficient_when_theme_unknown_in_table():
    state, _ = classify_thesis(_make(theme="some_new_theme"), theme_thesis={})
    assert state == "evidence_insufficient"


def test_thesis_uses_table_for_known_theme():
    state, _ = classify_thesis(
        _make(theme="semiconductor"),
        theme_thesis={"semiconductor": "intact"},
    )
    assert state == "intact"


def test_thesis_falsified_when_table_says_falsified():
    state, _ = classify_thesis(
        _make(theme="real_estate"),
        theme_thesis={"real_estate": "falsified"},
    )
    assert state == "falsified"


def test_thesis_degrades_to_under_pressure_on_style_drift():
    state, _ = classify_thesis(
        _make(theme="consumer", style_drift_flag=True),
        theme_thesis={"consumer": "intact"},
    )
    assert state == "under_pressure"


def test_thesis_degrades_to_evidence_insufficient_when_table_is_none():
    """LLM research failure path: theme_thesis=None must NOT crash."""
    state, _ = classify_thesis(_make(theme="semiconductor"), theme_thesis=None)
    assert state == "evidence_insufficient"


from irc.opportunity.states import classify_product_quality


def test_product_quality_strong_for_low_er_high_aum_passive():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.0015, aum_cny=10e9,
        tracking_error=0.001, premium_discount_pct=0.001,
    ))
    assert state == "strong"


def test_product_quality_acceptable_for_midband_passive():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.005, aum_cny=1e9,
        tracking_error=0.005, premium_discount_pct=0.005,
    ))
    assert state == "acceptable"


def test_product_quality_poor_for_high_er_tiny_aum():
    state, _ = classify_product_quality(_make(
        asset_class="cn_etf",
        expense_ratio=0.025, aum_cny=5e7,
    ))
    assert state == "poor"


def test_product_quality_insufficient_when_no_data():
    state, _ = classify_product_quality(_make(asset_class="cn_etf"))
    assert state == "evidence_insufficient"


def test_active_fund_demoted_when_manager_tenure_missing():
    """Active funds without tenure/style evidence cannot exceed 'weak'."""
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.012, aum_cny=2e9,
        manager_tenure_years=None,
    ))
    assert state in ("weak", "evidence_insufficient")


def test_active_fund_acceptable_when_tenure_and_aum_present():
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.012, aum_cny=2e9,
        manager_tenure_years=5.5, aum_stability_pct=0.85,
    ))
    assert state in ("acceptable", "strong")


from irc.opportunity.states import compose_opportunity_state, build_opportunity_row


def test_core_dca_when_cheap_cold_intact_acceptable():
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "core_dca"


def test_core_dca_when_reasonable_low_normal_intact_strong():
    state, _ = compose_opportunity_state(
        valuation="reasonable_low", heat="normal", thesis="intact",
        product_quality="strong",
    )
    assert state == "core_dca"


def test_exclude_when_thesis_falsified():
    """Spec test 3: cheap valuation + falsified thesis -> exclude."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="falsified",
        product_quality="strong",
    )
    assert state == "exclude"


def test_exclude_when_product_quality_poor():
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="poor",
    )
    assert state == "exclude"


def test_pause_wait_when_expensive_or_crowded():
    state, _ = compose_opportunity_state(
        valuation="expensive", heat="crowded", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "pause_wait"


def test_small_watch_when_evidence_insufficient_but_not_excluded():
    state, _ = compose_opportunity_state(
        valuation="reasonable_low", heat="normal",
        thesis="evidence_insufficient", product_quality="acceptable",
    )
    assert state == "small_watch"


def test_build_opportunity_row_records_evidence_gaps():
    """Spec test 9: missing data produces explicit typed evidence_gaps."""
    inp = _make(theme="semiconductor")
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert "missing_valuation_data" in row.evidence_gaps
    assert "missing_flow_or_return_data" in row.evidence_gaps
    assert "missing_product_metadata" in row.evidence_gaps


def test_build_opportunity_row_no_structural_gaps_when_metrics_present():
    """With all four classifier dimensions populated, the only remaining gaps
    are the thesis-fundamentals gaps (no snapshot / no theme report)."""
    inp = _make(
        theme="broad", tracked_index="csi300", asset_class="cn_etf",
        valuation_percentile_self=0.25,
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    row = build_opportunity_row(inp, theme_thesis={"broad": "intact"})
    structural = {"missing_valuation_data", "missing_flow_or_return_data", "missing_product_metadata"}
    assert structural.isdisjoint(set(row.evidence_gaps))


def test_venue_incompatible_does_not_block_core_dca():
    """venue_compatible=False no longer downgrades opportunity state; core_dca is still returned."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", venue_compatible=False,
    )
    assert state == "core_dca"


def test_venue_incompatible_does_not_affect_exclude():
    """Falsified thesis takes priority over venue incompatibility."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="falsified",
        product_quality="acceptable", venue_compatible=False,
    )
    assert state == "exclude"


def test_heat_gap_added_when_only_one_heat_input():
    """Issue 2 fix: n=1 heat inputs is evidence_insufficient, so gap must be flagged."""
    inp = _make(theme="semiconductor", ret_3m=0.05)  # only 1 of 6 heat signals
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert "missing_flow_or_return_data" in row.evidence_gaps


# ---------------------------------------------------------------------------
# Weak-link label in the catch-all small_watch reason
# ---------------------------------------------------------------------------


from irc.opportunity.states import build_opportunity_row, compose_opportunity_state


def test_compose_small_watch_reason_names_weak_product_quality():
    state, reason = compose_opportunity_state(
        valuation="reasonable_low",
        heat="cold",
        thesis="intact",
        product_quality="weak",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "产品质量薄弱" in reason
    assert reason.endswith("列入小仓位观察。")


def test_compose_small_watch_reason_names_weak_thesis():
    state, reason = compose_opportunity_state(
        valuation="fair",
        heat="normal",
        thesis="evidence_insufficient",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "主题逻辑证据不足" in reason


def test_compose_small_watch_reason_names_missing_valuation():
    state, reason = compose_opportunity_state(
        valuation="evidence_insufficient",
        heat="normal",
        thesis="intact",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "估值数据缺失" in reason


def test_compose_small_watch_reason_falls_back_on_conflict():
    """No single sub-state is weakest → generic 'signal conflict' label."""
    state, reason = compose_opportunity_state(
        valuation="fair",
        heat="normal",
        thesis="intact",
        product_quality="acceptable",
        venue_compatible=True,
    )
    assert state == "small_watch"
    assert "信号方向冲突" in reason


def test_build_opportunity_row_passes_asset_class_to_thesis_evidence():
    """A gold instrument with no snapshot picks up the refined label in expected_omissions."""
    from irc.opportunity.types import OpportunityInput

    inp = OpportunityInput(
        instrument_id="518880",
        asset_class="gold",
        market="cn_on_exchange",
        valuation_percentile_self=0.95,
        ret_1m=0.04,
        ret_3m=0.05,
    )
    row = build_opportunity_row(
        inp,
        theme_thesis=None,
        snapshot=None,
        theme_report=None,
    )
    assert "constituent_not_applicable" not in row.evidence_gaps
    assert "constituent_not_applicable" in row.expected_omissions


# ---------------------------------------------------------------------------
# build_opportunity_row + ConstituentSnapshot / ThemeReport integration
# ---------------------------------------------------------------------------

def _make_full_input(**overrides):
    """Build an input with all four classifier dimensions populated, so only the
    thesis path varies across the next tests."""
    base = dict(
        theme="semiconductor", tracked_index="csi300", asset_class="cn_etf",
        valuation_percentile_self=0.25,
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    base.update(overrides)
    return _make(**base)


def test_build_opportunity_row_uses_snapshot_when_provided():
    """When a ConstituentSnapshot is supplied, thesis state should be derived
    from concrete filings rather than the table."""
    from irc.fundamentals.types import ConstituentSnapshot, Constituent, FilingDigest
    filings = tuple(
        FilingDigest(symbol=f"S{i}", fiscal_period="Q1", filed_at_iso="2026-04-28",
                     revenue_yoy=-0.20, net_income_yoy=None, gross_margin=None,
                     source_url=f"https://x/{i}")
        for i in range(8)
    ) + tuple(
        FilingDigest(symbol=f"P{i}", fiscal_period="Q1", filed_at_iso="2026-04-28",
                     revenue_yoy=0.05, net_income_yoy=None, gross_margin=None,
                     source_url=f"https://x/p{i}")
        for i in range(2)
    )
    cons = tuple(Constituent(symbol=f.symbol, name=f.symbol, weight=0.05, market="cn") for f in filings)
    snap = ConstituentSnapshot(
        lookthrough_target="半导体", as_of_iso="2026-05-15",
        constituents=cons, filings=filings, broker_reports=(),
    )
    inp = _make_full_input()
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"}, snapshot=snap)
    assert row.thesis_state == "falsified"
    assert row.thesis_evidence  # populated, not empty
    assert any(e.type == "filing" for e in row.thesis_evidence)


def test_build_opportunity_row_falls_back_to_table_when_no_snapshot():
    """No snapshot → use the legacy table-based thesis classifier path."""
    inp = _make_full_input()
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.thesis_state == "intact"
    assert row.thesis_evidence == ()


def test_build_opportunity_row_marks_missing_snapshot_gap_when_table_used():
    """Even when the table says intact, mark missing_constituent_snapshot as a typed gap."""
    inp = _make_full_input()
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert "missing_constituent_snapshot" in row.evidence_gaps


# ---------------------------------------------------------------------------
# expected_omissions partition tests
# ---------------------------------------------------------------------------

from irc.opportunity.states import EXPECTED_OMISSION_CODES


def _gold_input(**over):
    base = dict(
        instrument_id="518880", name_cn="黄金ETF", asset_class="gold",
        market="cn_on_exchange",
    )
    base.update(over)
    return OpportunityInput(**base)


def test_constituent_not_applicable_lives_in_expected_omissions_for_gold():
    inp = _gold_input()
    row = build_opportunity_row(inp, theme_thesis=None, snapshot=None, theme_report=None)
    assert "constituent_not_applicable" not in row.evidence_gaps
    assert "constituent_not_applicable" in row.expected_omissions


def test_real_gaps_stay_in_evidence_gaps_for_indexable_asset_class():
    inp = _gold_input(asset_class="cn_etf", theme="broad")  # indexable
    row = build_opportunity_row(inp, theme_thesis=None, snapshot=None, theme_report=None)
    # For an indexable asset_class with no snapshot, 'constituent_missing' is a real gap
    assert "constituent_not_applicable" not in row.expected_omissions
    assert "constituent_not_applicable" not in row.evidence_gaps


# ── Item 003: build_opportunity_row with ActiveFundSnapshot ───────────────────

def test_build_opportunity_row_populates_constituent_analyses_for_active_fund() -> None:
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import (
        ConstituentAnalysis, OpportunityInput, ThesisEvidence,
    )
    ev = ThesisEvidence(
        type="filing", source="600519", url="https://x/a",
        date="2024-04-15", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="005827", parent_fund_id="005827",
        constituent_key="600519", holding_weight_pct=6.2,
    )
    c = ConstituentAnalysis("600519", "贵州茅台", 6.2, (ev,), (), "")
    snap = ActiveFundSnapshot(
        fund_id="005827", source_report_date="", source_report_quarter="2024Q1",
        cache_probed_at="", constituent_analyses=(c,),
        failure_reasons_by_symbol={},
    )
    inp = OpportunityInput(
        instrument_id="005827", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="易方达蓝筹精选",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert row.constituent_analyses == (c,)
    assert row.thesis_evidence == (ev,)


def test_expected_omission_codes_constant_documented():
    assert "constituent_not_applicable" in EXPECTED_OMISSION_CODES


# ---------------------------------------------------------------------------
# derive_contributing_dimensions — branch-table enumeration (Slice A0)
# ---------------------------------------------------------------------------

from irc.opportunity.states import derive_contributing_dimensions


@pytest.mark.parametrize(
    "valuation,heat,thesis,product,opportunity_state,expected",
    [
        # exclude branch — thesis and/or product trigger
        ("cheap", "cold", "falsified", "acceptable", "exclude", frozenset({"thesis"})),
        ("cheap", "cold", "intact", "poor", "exclude", frozenset({"product_quality"})),
        ("cheap", "cold", "falsified", "poor", "exclude", frozenset({"thesis", "product_quality"})),
        # core_dca branch — all four dimensions are drivers
        (
            "cheap", "normal", "intact", "strong", "core_dca",
            frozenset({"valuation", "heat", "thesis", "product_quality"}),
        ),
        # pause_wait branch — subset of {valuation, heat}
        ("expensive", "normal", "intact", "acceptable", "pause_wait", frozenset({"valuation"})),
        ("cheap", "crowded", "intact", "acceptable", "pause_wait", frozenset({"heat"})),
        (
            "expensive", "overheated", "intact", "acceptable", "pause_wait",
            frozenset({"valuation", "heat"}),
        ),
        # small_watch branch — priority chain: product_quality → thesis → valuation → heat → conflict
        ("fair", "normal", "intact", "weak", "small_watch", frozenset({"product_quality"})),
        (
            "fair", "normal", "evidence_insufficient", "acceptable", "small_watch",
            frozenset({"thesis"}),
        ),
        (
            "evidence_insufficient", "normal", "intact", "acceptable", "small_watch",
            frozenset({"valuation"}),
        ),
        (
            "fair", "evidence_insufficient", "intact", "acceptable", "small_watch",
            frozenset({"heat"}),
        ),
        # small_watch conflict — no single weak link
        ("fair", "normal", "intact", "acceptable", "small_watch", frozenset()),
    ],
)
def test_derive_contributing_dimensions_branch_table(
    valuation, heat, thesis, product, opportunity_state, expected,
):
    result = derive_contributing_dimensions(
        valuation, heat, thesis, product, opportunity_state,
    )
    assert result == expected


def test_derive_contributing_dimensions_returns_frozenset_not_set():
    """AC #6: equality is blind to set-vs-frozenset because `set({"a"}) ==
    frozenset({"a"})` is True. OpportunityRow is a frozen dataclass, so a
    mutable set field would silently break hashability."""
    result = derive_contributing_dimensions(
        "cheap", "normal", "intact", "strong", "core_dca",
    )
    assert isinstance(result, frozenset)


def test_build_opportunity_row_populates_contributing_dimensions_for_core_dca():
    """AC #5: end-to-end propagation through build_opportunity_row. A clean
    core_dca input must surface all four dimensions."""
    inp = _make_full_input(valuation_percentile_self=0.15)  # cheap → core_dca
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.opportunity_state == "core_dca"
    assert row.contributing_dimensions == frozenset(
        {"valuation", "heat", "thesis", "product_quality"},
    )
    assert isinstance(row.contributing_dimensions, frozenset)
