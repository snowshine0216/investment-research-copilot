from __future__ import annotations
import pytest

from irc.opportunity.states import COMMODITY_CYCLICAL_THEMES, classify_valuation
from irc.opportunity.types import OpportunityInput


def _make(**kwargs) -> OpportunityInput:
    base = {"instrument_id": "X", "asset_class": "cn_etf", "market": "cn_on_exchange"}
    base.update(kwargs)
    return OpportunityInput(**base)


def test_opportunity_input_has_fundamental_percentile_fields_defaulting_none():
    inp = _make()
    assert inp.valuation_percentile_fundamental is None
    assert inp.valuation_percentile_fundamental_pb is None


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


from irc.opportunity.states import (
    VALUATION_DIVERGENCE_CODE,
    valuation_divergence_code,
)


def _div(**kwargs):
    return _make(asset_class="cn_etf", market="cn_on_exchange", **kwargs)


def test_divergence_none_when_either_percentile_missing():
    assert valuation_divergence_code(_div(valuation_percentile_fundamental=0.1)) is None
    assert valuation_divergence_code(_div(valuation_percentile_self=0.1)) is None
    assert valuation_divergence_code(_div()) is None


def test_divergence_none_when_same_band_and_small_gap():
    # both in `fair` band (0.40..0.70), gap 0.05 < 0.25
    inp = _div(valuation_percentile_fundamental=0.50, valuation_percentile_self=0.55)
    assert valuation_divergence_code(inp) is None


def test_divergence_fires_on_band_tier_crossing():
    # fundamental cheap (<0.20), self fair (0.40..0.70); gap 0.45 also >= 0.25
    inp = _div(valuation_percentile_fundamental=0.10, valuation_percentile_self=0.55)
    assert valuation_divergence_code(inp) == VALUATION_DIVERGENCE_CODE


def test_divergence_fires_on_large_gap_within_same_band():
    # NOTE: choose two values in the SAME band but >= 0.25 apart.
    # fair band spans 0.40..0.70 (width 0.30) → 0.41 and 0.69 are both `fair`,
    # gap 0.28 >= 0.25 → divergence by the gap rule alone.
    inp = _div(valuation_percentile_fundamental=0.41, valuation_percentile_self=0.69)
    assert valuation_divergence_code(inp) == VALUATION_DIVERGENCE_CODE


def test_fundamental_percentile_decides_each_band():
    # When valuation_percentile_fundamental is present it OVERRIDES the NAV pct.
    cases = {
        0.10: "cheap",
        0.30: "reasonable_low",
        0.55: "fair",
        0.80: "expensive",
        0.95: "very_expensive",
    }
    for fund_pct, expected in cases.items():
        inp = _make(
            valuation_percentile_fundamental=fund_pct,
            valuation_percentile_self=0.50,  # deliberately disagrees
        )
        state, _ = classify_valuation(inp)
        assert state == expected, (fund_pct, state)


def test_fundamental_none_falls_back_to_nav_byte_for_byte():
    # Regression lock (AC2): no fundamental pct → identical to today's NAV path.
    inp = _make(valuation_percentile_fundamental=None, valuation_percentile_self=0.95)
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    # The fallback path must not mention the fundamental percentile.
    assert "PE 百分位" not in reason


def test_classify_valuation_appends_divergence_note_without_signature_change():
    inp = _make(
        valuation_percentile_fundamental=0.10,  # cheap
        valuation_percentile_self=0.85,          # expensive
    )
    out = classify_valuation(inp)
    assert isinstance(out, tuple) and len(out) == 2
    state, reason = out
    assert state == "cheap"  # fundamental decides
    assert "背离" in reason  # divergence caveat present


def test_pb_corroboration_note_appears_without_changing_state():
    # PE-band cheap but PB percentile >= 0.70 → cyclical-earnings caveat, state stays cheap.
    inp = _make(
        valuation_percentile_fundamental=0.10,
        valuation_percentile_fundamental_pb=0.85,
        valuation_percentile_self=0.10,  # agree → no divergence note
    )
    state, reason = classify_valuation(inp)
    assert state == "cheap"
    assert "PB" in reason


# ---------------------------------------------------------------------------
# §1 commodity-cyclical NAV-anchor exclusion (symmetric guard)
# ---------------------------------------------------------------------------

def test_commodity_cyclical_themes_is_metals_only():
    # Locked membership: the guard is bound to the theme set, not a shortlist.
    assert COMMODITY_CYCLICAL_THEMES == frozenset({"metals"})


def test_metals_no_fundamental_anchor_withholds_low_nav_would_be_cheap():
    # Low NAV percentile would read `cheap` — symmetric guard withholds it.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.05,
    )
    state, reason = classify_valuation(inp)
    assert state == "evidence_insufficient"
    assert "锚" in reason or "动量" in reason


def test_metals_no_fundamental_anchor_withholds_high_nav_would_be_very_expensive():
    # High NAV percentile would read `very_expensive` — symmetric guard withholds it.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "evidence_insufficient"


def test_metals_guard_covers_qdii_global_cross_asset_class():
    # qdii_global is in _EQUITY_ASSET_CLASSES; a metals-themed QDII (378546) is guarded too.
    inp = _make(
        asset_class="qdii_global",
        theme="metals",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "evidence_insufficient"


def test_metals_with_pe_anchor_skips_guard_and_uses_pe_rule():
    # A metals fund that HAS a PE anchor uses the existing PE band rule.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="metals",
        valuation_percentile_fundamental=0.05,  # PE cheap
        valuation_percentile_self=0.97,          # NAV high (ignored)
    )
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_non_metals_equity_no_regression_keeps_nav_banding():
    # A non-metals equity fund with no fundamental anchor still bands off NAV.
    inp = _make(
        asset_class="cn_equity_fund",
        theme="semiconductor",
        valuation_percentile_fundamental=None,
        valuation_percentile_self=0.97,
    )
    state, _ = classify_valuation(inp)
    assert state == "very_expensive"


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


def test_active_fund_not_floored_to_weak_when_cost_scale_sound_and_aum_stability_missing():
    """F-1 floor removal: a sound active fund (low fee, large AUM, adequate
    tenure) must NOT be floored to 'weak' just because aum_stability_pct is
    absent. Missing AUM-stability caps the ceiling at 'acceptable' (it cannot
    reach 'strong'), but never floors a genuinely sound product."""
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.008, aum_cny=5e9,
        manager_tenure_years=6.0, aum_stability_pct=None,
    ))
    assert state == "acceptable"


def test_active_fund_strong_requires_present_low_aum_stability():
    """Regression guard for the active 'strong' gate: it needs score>=0.5 AND
    tenure>=5 AND aum_stability_pct present & <= _AUM_STABILITY_STRONG_MAX. This
    path is dead in production today (aum_stability_pct is never ingested) but the
    threshold is live logic — pin it so F-1 ingestion can't silently regress it."""
    state, _ = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.005, aum_cny=1e10,
        manager_tenure_years=6.0, aum_stability_pct=0.10,
    ))
    assert state == "strong"


def test_active_fund_weak_reason_reflects_cost_scale_when_genuinely_weak():
    """A genuinely weak active fund (small AUM, mediocre fee) stays 'weak',
    but the reason must attribute it to real cost/scale weakness — not to the
    removed 'missing AUM-stability evidence' floor."""
    state, reason = classify_product_quality(_make(
        asset_class="cn_equity_fund",
        market="cn_off_exchange",
        expense_ratio=0.014, aum_cny=166_000_000.0,
        manager_tenure_years=8.5, aum_stability_pct=None,
    ))
    assert state == "weak"
    assert "成本" in reason or "规模" in reason


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


def test_core_dca_blocked_when_fundamental_rich():
    """AC4: cheap percentile + 'rich' fundamental → NOT core_dca (falls to small_watch).

    The percentile fact (`valuation == cheap`) stays true; only the opportunity
    state falls through. Threading is the explicit composer parameter (grill Q-T2).
    """
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental="rich",
    )
    assert state == "small_watch"


def test_core_dca_allowed_when_fundamental_neutral():
    """AC4: only 'rich' blocks; neutral/cheap/None keep the core_dca path."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental="neutral",
    )
    assert state == "core_dca"


def test_core_dca_default_param_keeps_existing_callers_green():
    """AC4: default None keeps every existing caller byte-identical (dormancy)."""
    state, _ = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert state == "core_dca"


def test_fundamental_rich_does_not_change_pause_wait():
    """AC4/AC5: the block only suppresses core_dca; an expensive row is
    pause_wait regardless of the fundamental signal."""
    state, _ = compose_opportunity_state(
        valuation="expensive", heat="normal", thesis="intact",
        product_quality="acceptable", valuation_fundamental="rich",
    )
    assert state == "pause_wait"


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


def test_no_missing_valuation_gap_when_fundamental_percentile_present():
    """Finding 1 fix: fundamental percentile alone is sufficient valuation data.

    A broad-index ETF with a warm index_valuation_history cache gives
    valuation_percentile_fundamental but a failed price/NAV fetch leaves
    valuation_percentile_self and valuation_percentile_vs_benchmark None.
    _structural_evidence_gaps must NOT flag missing_valuation_data, because the
    fundamental percentile gives a valid valuation verdict via classify_valuation.
    Row must be publishable (no missing_valuation_data in evidence_gaps).
    """
    inp = _make(
        theme="broad", tracked_index="csi300", asset_class="cn_etf",
        # No price/NAV percentile — simulates failed price fetch
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=None,
        # Fundamental percentile present from warm index_valuation_history cache
        valuation_percentile_fundamental=0.10,
        # Enough heat signals (>=2) and product metadata so row is otherwise publishable
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    row = build_opportunity_row(inp, theme_thesis={"broad": "intact"})
    assert "missing_valuation_data" not in row.evidence_gaps


def test_missing_valuation_gap_when_all_three_percentiles_none():
    """Regression: when ALL THREE valuation percentiles are None, the gap MUST
    still be flagged. This preserves the existing behavior."""
    inp = _make(
        theme="broad", tracked_index="csi300", asset_class="cn_etf",
        valuation_percentile_self=None,
        valuation_percentile_vs_benchmark=None,
        valuation_percentile_fundamental=None,
        ret_3m=0.02, ret_6m=0.05,
        expense_ratio=0.0015, aum_cny=20e9,
    )
    row = build_opportunity_row(inp, theme_thesis={"broad": "intact"})
    assert "missing_valuation_data" in row.evidence_gaps


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


def test_build_opportunity_row_records_active_fund_fetch_types_attempted() -> None:
    """Rejected active-fund rows must not render as 已尝试: (none) when the
    snapshot proves holdings, filing, broker, and news fetch paths ran."""
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import (
        ConstituentAnalysis, OpportunityInput, ThesisEvidence,
    )
    ev = ThesisEvidence(
        type="filing", source="300903", url="https://x/a",
        date="2026-03-31", summary="x",
        scope="constituent", citation_kind="data",
        owner_instrument_id="001877", parent_fund_id="001877",
        constituent_key="300903", holding_weight_pct=5.72,
    )
    c = ConstituentAnalysis(
        "300903", "科翔股份", 5.72, (ev,),
        ("broker_empty:300903", "news_fetch_failed:300903:ArrowInvalid"),
        "300903.SZ 2026Q1 revenue",
    )
    snap = ActiveFundSnapshot(
        fund_id="001877", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="2026-05-24",
        constituent_analyses=(c,), failure_reasons_by_symbol={},
    )
    inp = OpportunityInput(
        instrument_id="001877", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="宝盈国家安全沪港深股票A",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert row.fetch_types_attempted == ("holdings", "filing", "broker", "news")


def test_build_opportunity_row_records_holdings_fetch_attempt_on_empty_active_snapshot() -> None:
    from irc.fundamentals.types import ActiveFundSnapshot
    from irc.opportunity.states import build_opportunity_row
    from irc.opportunity.types import OpportunityInput

    snap = ActiveFundSnapshot(
        fund_id="004814", source_report_date="", source_report_quarter="",
        cache_probed_at="2026-05-24", constituent_analyses=(),
        failure_reasons_by_symbol={},
        fund_level_failure_reasons=("holdings_fetch_failed:004814:empty",),
    )
    inp = OpportunityInput(
        instrument_id="004814", asset_class="cn_equity_fund",
        market="cn_off_exchange", name_cn="中欧红利优享混合A",
    )
    row = build_opportunity_row(inp, None, snapshot=snap)
    assert row.fetch_types_attempted == ("holdings",)


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


def test_build_opportunity_row_core_dca_when_consensus_upside_none():
    """AC6: all-None fundamentals → cheap percentile core_dca, unchanged."""
    inp = _make_full_input(valuation_percentile_self=0.15)  # cheap percentile
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.valuation_state == "cheap"
    assert row.opportunity_state == "core_dca"


def test_build_opportunity_row_blocks_core_dca_when_fundamental_rich():
    """AC4 end-to-end: cheap percentile + rich consensus upside →
    valuation_state STAYS cheap, opportunity_state falls to small_watch,
    reason annotates the contradiction. No new ThesisEvidence (AC8)."""
    inp = _make_full_input(
        valuation_percentile_self=0.15,  # cheap percentile (fact stays true)
        consensus_upside_pct=-0.30,      # 'rich' → contradiction
    )
    row = build_opportunity_row(inp, theme_thesis={"semiconductor": "intact"})
    assert row.valuation_state == "cheap"          # AC3-preserving
    assert row.opportunity_state == "small_watch"  # AC4 block
    assert "下行" in row.opportunity_reason         # contradiction annotated
    assert row.thesis_evidence == ()               # AC8: no citation surface
    assert row.evidence_gaps  # only the pre-existing snapshot/news gaps; no new gap


def test_opportunity_row_default_advisory_gaps_is_empty_tuple():
    """ADR 0005: `advisory_gaps` is a tuple[str, ...] that defaults to ()."""
    from irc.fundamentals.types import LookthroughTarget
    from irc.opportunity.types import OpportunityRow

    row = OpportunityRow(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        lookthrough_target=LookthroughTarget(
            kind="broad_index", key="x", display_cn="x", provider_symbol="",
        ),
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        opportunity_reason="", evidence_gaps=(),
    )
    assert row.advisory_gaps == ()


def test_thesis_card_default_advisory_gaps_is_empty_tuple():
    from irc.opportunity.types import ThesisCard

    card = ThesisCard(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        role="", lookthrough_target="x", entry_reason="",
        valuation_state="fair", heat_state="normal", thesis_state="intact",
        product_quality_state="acceptable", opportunity_state="core_dca",
        dca_action="normal_dca", risk_action="none",
        falsification_triggers=(), trim_triggers=(),
        do_not_sell_just_because=(), review_cadence="weekly_light_monthly_full",
        evidence_gaps=(),
    )
    assert card.advisory_gaps == ()


def test_discipline_row_default_advisory_gaps_is_empty_tuple():
    from irc.opportunity.types import DisciplineRow

    drow = DisciplineRow(
        instrument_id="x", name_cn="x", asset_class="cn_etf", theme=None,
        opportunity_state="core_dca", dca_action="normal_dca",
        risk_action="none", note_cn="",
    )
    assert drow.advisory_gaps == ()


def test_partition_gaps_returns_3_tuple_with_advisory():
    from irc.opportunity.states import _partition_gaps
    real, expected, advisory = _partition_gaps((
        "missing_broker_coverage",
        "constituent_not_applicable",
        "top_holdings_broker_thin",
    ))
    assert real == ("missing_broker_coverage",)
    assert expected == ("constituent_not_applicable",)
    assert advisory == ("top_holdings_broker_thin",)


def test_partition_gaps_empty_input_returns_three_empty_tuples():
    from irc.opportunity.states import _partition_gaps
    assert _partition_gaps(()) == ((), (), ())


def test_advisory_gap_codes_re_exported_from_states():
    from irc.opportunity.states import ADVISORY_GAP_CODES
    assert "top_holdings_broker_thin" in ADVISORY_GAP_CODES


def test_build_opportunity_row_snapshot_annotation_includes_fund_level() -> None:
    """RD-6a: the snapshot param must declare FundLevelSnapshot (production passes one)."""
    import typing

    from irc.fundamentals.types import FundLevelSnapshot
    from irc.opportunity.states import build_opportunity_row

    hints = typing.get_type_hints(build_opportunity_row)
    assert FundLevelSnapshot in typing.get_args(hints["snapshot"])


# ---------------------------------------------------------------------------
# Task 10: thread divergence into build_opportunity_row (R2/H3)
# ---------------------------------------------------------------------------

def _broad_index_inp(**kwargs):
    base = dict(
        instrument_id="510300",
        asset_class="cn_etf",
        market="cn_on_exchange",
        name_cn="沪深300ETF",
        tracked_index="csi300",
        # enough heat + product signals so the row is otherwise publishable
        ret_1m=0.0, ret_3m=0.0, expense_ratio=0.005, aum_cny=5.0e10,
    )
    base.update(kwargs)
    return OpportunityInput(**base)


def test_build_row_routes_divergence_to_advisory_not_evidence_gaps():
    inp = _broad_index_inp(
        valuation_percentile_fundamental=0.10,  # cheap
        valuation_percentile_self=0.85,          # expensive → divergence
    )
    # theme_thesis provided so classify_thesis has a table; snapshot=None path.
    row = build_opportunity_row(inp, {"宽基": "intact"})
    assert "valuation_price_fundamental_divergence" in row.advisory_gaps
    assert "valuation_price_fundamental_divergence" not in row.evidence_gaps


def test_build_row_no_divergence_code_when_percentiles_agree():
    inp = _broad_index_inp(
        valuation_percentile_fundamental=0.10,
        valuation_percentile_self=0.12,  # agree → no divergence
    )
    row = build_opportunity_row(inp, {"宽基": "intact"})
    assert "valuation_price_fundamental_divergence" not in row.advisory_gaps
