"""Symmetric trim-side discipline triggers (item 012, 2026-05-19).

Adversarial review §F: every equity in the 2026-05-19 memo was already
very_expensive but none carried risk=trim_review. The trim path was
gated on overweight (portfolio_weight > target_band_high) which is
rarely true for a system that hasn't opened positions yet.
"""
from __future__ import annotations

import pytest

from irc.opportunity.discipline import (
    PositionContext,
    derive_risk_action,
)
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(
    *,
    valuation_state="fair",
    heat_state="normal",
    thesis_state="intact",
    product_quality_state="strong",
    opportunity_state="core_dca",
) -> OpportunityRow:
    return OpportunityRow(
        instrument_id="X",
        name_cn="X",
        asset_class="us_etf",
        theme=None,
        lookthrough_target=LookthroughTarget(kind="broad_index", key="sp500", display_cn="S&P 500"),
        valuation_state=valuation_state,
        heat_state=heat_state,
        thesis_state=thesis_state,
        product_quality_state=product_quality_state,
        opportunity_state=opportunity_state,
        opportunity_reason="",
        evidence_gaps=(),
    )


def _pos(
    *,
    is_holding=False,
    portfolio_weight=None,
    target_band_high=None,
    drawdown_since_entry=None,
) -> PositionContext:
    return PositionContext(
        portfolio_weight=portfolio_weight,
        target_band_low=None,
        target_band_high=target_band_high,
        drawdown_since_entry=drawdown_since_entry,
        is_holding=is_holding,
    )


def test_very_expensive_holding_emits_trim_review() -> None:
    """The 2026-05-19 case: equity at very_expensive, user holds it
    within band → trim_review fires (was 'none' under the old rule)."""
    action = derive_risk_action(
        _row(valuation_state="very_expensive"),
        _pos(is_holding=True),
    )
    assert action == "trim_review"


def test_crowded_holding_emits_trim_review() -> None:
    action = derive_risk_action(
        _row(heat_state="crowded"),
        _pos(is_holding=True),
    )
    assert action == "trim_review"


def test_very_expensive_non_holding_returns_none() -> None:
    """A row the user does NOT own with very_expensive valuation doesn't
    trigger trim_review (nothing to trim) — DCA pause is the right
    signal there, not risk action."""
    action = derive_risk_action(
        _row(valuation_state="very_expensive"),
        _pos(is_holding=False),
    )
    assert action == "none"


def test_overweight_legacy_path_still_fires() -> None:
    """Legacy: overweight + expensive remains trim_review even when
    is_holding wasn't set explicitly (back-compat for callers that
    pre-date this change)."""
    action = derive_risk_action(
        _row(valuation_state="expensive"),
        _pos(portfolio_weight=0.12, target_band_high=0.10),
    )
    assert action == "trim_review"


def test_fair_holding_returns_none() -> None:
    action = derive_risk_action(
        _row(valuation_state="fair", heat_state="normal"),
        _pos(is_holding=True),
    )
    assert action == "none"


def test_falsified_thesis_dominates_with_exit_review() -> None:
    """Falsified > trim_review; the symmetric trim rule must not mask
    a stronger exit signal."""
    action = derive_risk_action(
        _row(valuation_state="very_expensive", thesis_state="falsified"),
        _pos(is_holding=True),
    )
    assert action == "exit_review"
