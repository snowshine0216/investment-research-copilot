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
    """Spec test 9: missing data produces explicit evidence_gaps."""
    inp = _make(theme="semiconductor")
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert "valuation" in row.evidence_gaps
    assert "heat" in row.evidence_gaps
    assert "product_quality" in row.evidence_gaps


def test_build_opportunity_row_no_gaps_when_evidence_present():
    inp = _make(
        theme="broad", tracked_index="csi300", asset_class="cn_etf",
        valuation_percentile_self=0.25,
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    row = build_opportunity_row(inp, theme_thesis={"broad": "intact"})
    assert row.evidence_gaps == ()


def test_venue_incompatible_demotes_core_dca_to_small_watch():
    """Issue 1 fix: venue_compatible=False must not produce core_dca."""
    state, reason = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", venue_compatible=False,
    )
    assert state == "small_watch"
    assert "渠道" in reason or "观察" in reason


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
    assert "heat" in row.evidence_gaps
