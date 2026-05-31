"""Item 002 — pure fundamental valuation anchor over `consensus_upside_pct`.

Spec: docs/2026-05-31-funding-analysis/items/002-spec.md (AC1).
ADR 0009: the input is `None` in production today → signal `None` (no opinion).
"""
from __future__ import annotations

import dataclasses

from irc.opportunity.states import build_opportunity_row, classify_valuation, compose_opportunity_state
from irc.opportunity.types import OpportunityInput
from irc.opportunity.valuation_fundamental import (
    CHEAP_UPSIDE_THRESHOLD,
    RICH_UPSIDE_THRESHOLD,
    _fundamental_reason_phrase,
    valuation_fundamental_signal,
)


def _equity(**kwargs) -> OpportunityInput:
    base = dict(instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange")
    base.update(kwargs)
    return OpportunityInput(**base)


def test_thresholds_are_ratio_constants() -> None:
    assert CHEAP_UPSIDE_THRESHOLD == 0.20
    assert RICH_UPSIDE_THRESHOLD == -0.10


def test_signal_cheap_at_and_above_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.20)) == "cheap"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.25)) == "cheap"


def test_signal_rich_at_and_below_threshold() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.10)) == "rich"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.30)) == "rich"


def test_signal_neutral_between_thresholds() -> None:
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=0.05)) == "neutral"
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=-0.05)) == "neutral"


def test_signal_none_when_input_none() -> None:
    """Production-today case (ADR 0009): no target price → no opinion."""
    assert valuation_fundamental_signal(_equity(consensus_upside_pct=None)) is None
    assert valuation_fundamental_signal(_equity()) is None


def test_reason_phrase_cheap_mentions_upside() -> None:
    phrase = _fundamental_reason_phrase("cheap", _equity(consensus_upside_pct=0.25))
    assert "上行空间" in phrase
    assert "便宜" in phrase
    assert "25%" in phrase  # ratio rendered as percent for humans


def test_reason_phrase_rich_mentions_downside() -> None:
    phrase = _fundamental_reason_phrase("rich", _equity(consensus_upside_pct=-0.30))
    assert "目标价" in phrase or "下行" in phrase
    assert "-30%" in phrase


def test_reason_phrase_appends_pe_pb_when_present() -> None:
    phrase = _fundamental_reason_phrase(
        "neutral", _equity(consensus_upside_pct=0.05, pe_ttm=12.1, pb=1.31)
    )
    assert "PE 12.1" in phrase
    assert "PB 1.31" in phrase


def test_reason_phrase_omits_pe_pb_when_absent() -> None:
    phrase = _fundamental_reason_phrase("neutral", _equity(consensus_upside_pct=0.05))
    assert "PE" not in phrase
    assert "PB" not in phrase


def test_classify_valuation_appends_fundamental_phrase_for_equity() -> None:
    """AC2: equity with consensus_upside_pct gets the 便宜/上行空间 caveat."""
    inp = _equity(valuation_percentile_self=0.55, consensus_upside_pct=0.25)
    state, reason = classify_valuation(inp)
    assert state == "fair"  # AC3: no notch from a `fair` percentile
    assert "上行空间" in reason


def test_classify_valuation_no_fundamental_phrase_for_bond_class() -> None:
    """AC5: bonds use the yield-percentile anchor — fundamental caveat never fires.

    Mirrors test_classify_valuation_does_not_append_phrase_for_bond_class.
    """
    inp = OpportunityInput(
        instrument_id="000111", asset_class="cn_bond_fund", market="CN",
        cn_bond_yield_percentile=0.05, consensus_upside_pct=0.25,
    )
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    assert "上行空间" not in reason


def test_classify_valuation_no_fundamental_phrase_when_signal_none() -> None:
    """AC6: consensus_upside_pct None → no caveat, byte-identical to today."""
    inp = _equity(valuation_percentile_self=0.55)
    state, reason = classify_valuation(inp)
    assert state == "fair"
    assert "上行空间" not in reason


def test_notch_reasonable_low_plus_cheap_signal_becomes_cheap() -> None:
    """AC3(a): percentile reasonable_low + 'cheap' signal → cheap (corroboration)."""
    inp = _equity(valuation_percentile_self=0.30, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_notch_cheap_plus_cheap_signal_stays_cheap() -> None:
    """AC3: already cheap stays cheap (notch is a no-op, never moves expensive)."""
    inp = _equity(valuation_percentile_self=0.10, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "cheap"


def test_notch_does_not_fire_for_fair_percentile() -> None:
    """AC3(b): percentile fair + 'cheap' signal → fair (no jump)."""
    inp = _equity(valuation_percentile_self=0.55, consensus_upside_pct=0.25)
    state, _ = classify_valuation(inp)
    assert state == "fair"


def test_notch_never_moves_toward_more_expensive() -> None:
    """AC3(c): percentile expensive + 'rich' signal → expensive (reason only)."""
    inp = _equity(valuation_percentile_self=0.80, consensus_upside_pct=-0.30)
    state, reason = classify_valuation(inp)
    assert state == "expensive"
    assert "下行" in reason  # contradiction annotated


def test_notch_does_not_fire_for_neutral_signal() -> None:
    """AC3: corroboration requires signal=='cheap'; neutral leaves state alone."""
    inp = _equity(valuation_percentile_self=0.30, consensus_upside_pct=0.05)
    state, _ = classify_valuation(inp)
    assert state == "reasonable_low"


def test_notch_does_not_fire_when_signal_none() -> None:
    """AC6: None signal → state byte-identical to today (dormant)."""
    inp = _equity(valuation_percentile_self=0.30)
    state, _ = classify_valuation(inp)
    assert state == "reasonable_low"


def test_bond_classify_byte_identical_with_consensus_upside_set() -> None:
    """AC5: bonds are yield-percentile-anchored; consensus_upside_pct must not
    change classify_valuation output (bond-valuation invariant)."""
    bare = OpportunityInput(
        instrument_id="014502", asset_class="cn_bond_fund", market="cn_off_exchange",
        cn_bond_yield_percentile=0.65,
    )
    populated = dataclasses.replace(bare, consensus_upside_pct=0.25, pe_ttm=8.0, pb=0.9)
    assert classify_valuation(populated) == classify_valuation(bare)


def test_gold_classify_byte_identical_with_consensus_upside_set() -> None:
    """AC5: gold has no equity fundamentals; the anchor must not fire."""
    bare = OpportunityInput(
        instrument_id="518880", asset_class="gold", market="cn_on_exchange",
        valuation_percentile_self=0.50,
    )
    populated = dataclasses.replace(bare, consensus_upside_pct=-0.30)
    assert classify_valuation(populated) == classify_valuation(bare)


def test_compose_state_block_inert_for_none_fundamental() -> None:
    """AC5/AC6: the composer block is keyed on valuation_fundamental only; a
    bond/gold row never supplies it → core_dca path unchanged."""
    with_none = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable", valuation_fundamental=None,
    )
    legacy = compose_opportunity_state(
        valuation="cheap", heat="cold", thesis="intact",
        product_quality="acceptable",
    )
    assert with_none == legacy == ("core_dca", with_none[1])


def test_fundamental_block_emits_no_thesis_evidence_or_gap(monkeypatch):
    """AC8: the valuation/core_dca path emits NO new ThesisEvidence and NO new
    gap code; H3 partition (evidence_gaps), SAME-3 (citation set), Policy B,
    and thesis_state derivation are structurally untouched.

    Compare a rich-blocked row against the same row with the fundamental input
    cleared: thesis_evidence, evidence_gaps, expected_omissions, advisory_gaps,
    contributing_dimensions, and thesis_state must be IDENTICAL (only
    opportunity_state / opportunity_reason may differ)."""
    base = OpportunityInput(
        instrument_id="510300", asset_class="cn_etf", market="cn_on_exchange",
        theme="semiconductor", tracked_index="csi300",
        valuation_percentile_self=0.15,  # cheap percentile
        ret_3m=0.02, ret_6m=0.05, expense_ratio=0.0015, aum_cny=20e9,
    )
    rich = dataclasses.replace(base, consensus_upside_pct=-0.30)  # 'rich' block
    none_row = build_opportunity_row(base, theme_thesis={"semiconductor": "intact"})
    rich_row = build_opportunity_row(rich, theme_thesis={"semiconductor": "intact"})

    # The block changes opportunity_state + reason ONLY.
    assert none_row.opportunity_state == "core_dca"
    assert rich_row.opportunity_state == "small_watch"
    # Everything citation/gap/thesis-shaped is byte-identical.
    assert rich_row.thesis_evidence == none_row.thesis_evidence == ()
    assert rich_row.evidence_gaps == none_row.evidence_gaps
    assert rich_row.expected_omissions == none_row.expected_omissions
    assert rich_row.advisory_gaps == none_row.advisory_gaps
    assert rich_row.thesis_state == none_row.thesis_state  # owned by derive_thesis_from_evidence
    # valuation_state stays cheap on both (AC3-preserving).
    assert rich_row.valuation_state == none_row.valuation_state == "cheap"
