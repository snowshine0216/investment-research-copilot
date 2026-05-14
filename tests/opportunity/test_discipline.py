from __future__ import annotations
import pytest

from irc.opportunity.discipline import (
    derive_dca_action,
    derive_risk_action,
    PositionContext,
)
from irc.opportunity.types import LookthroughTarget, OpportunityRow


def _row(**overrides) -> OpportunityRow:
    base = dict(
        instrument_id="510300",
        name_cn="X",
        asset_class="cn_etf",
        theme="broad",
        lookthrough_target=LookthroughTarget("broad_index", "csi300", "沪深300"),
        valuation_state="reasonable_low",
        heat_state="normal",
        thesis_state="intact",
        product_quality_state="acceptable",
        opportunity_state="core_dca",
        opportunity_reason="",
        evidence_gaps=(),
    )
    base.update(overrides)
    return OpportunityRow(**base)


def _pos(weight: float, band_high: float, *, drawdown: float = 0.0) -> PositionContext:
    return PositionContext(
        portfolio_weight=weight,
        target_band_low=0.0,
        target_band_high=band_high,
        drawdown_since_entry=drawdown,
        is_holding=True,
    )


def test_accelerate_when_cheap_cold_intact_strong():
    action = derive_dca_action(_row(
        valuation_state="cheap", heat_state="cold",
        thesis_state="intact", product_quality_state="strong",
        opportunity_state="core_dca",
    ))
    assert action == "accelerate_dca"


def test_normal_dca_when_reasonable_low_normal():
    action = derive_dca_action(_row(opportunity_state="core_dca"))
    assert action == "normal_dca"


def test_pause_when_under_pressure_thesis():
    action = derive_dca_action(_row(thesis_state="under_pressure"))
    assert action == "pause_dca"


def test_pause_when_expensive():
    action = derive_dca_action(_row(
        valuation_state="expensive", heat_state="crowded",
        opportunity_state="pause_wait",
    ))
    assert action == "pause_dca"


def test_do_not_buy_when_excluded():
    action = derive_dca_action(_row(
        thesis_state="falsified", opportunity_state="exclude",
    ))
    assert action == "do_not_buy"


def test_drawdown_alone_only_triggers_review_required():
    """Spec test 4: drawdown of 20% does NOT produce sell/exit by itself."""
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30, drawdown=0.22),
    )
    assert action == "review_required"


def test_drawdown_50_still_not_auto_exit():
    """Even a catastrophic drawdown alone must NOT escalate to exit_review
    when thesis remains intact and product is acceptable."""
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30, drawdown=0.50),
    )
    assert action == "review_required"


def test_expensive_crowded_overweight_produces_trim_review():
    """Spec test 5: expensive + crowded + overweight => trim_review."""
    action = derive_risk_action(
        _row(
            valuation_state="expensive", heat_state="crowded",
            opportunity_state="pause_wait",
        ),
        _pos(weight=0.40, band_high=0.30),
    )
    assert action == "trim_review"


def test_falsified_thesis_produces_exit_review():
    action = derive_risk_action(
        _row(thesis_state="falsified", opportunity_state="exclude"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "exit_review"


def test_poor_product_quality_produces_exit_review():
    action = derive_risk_action(
        _row(product_quality_state="poor", opportunity_state="exclude"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "exit_review"


def test_no_risk_action_when_state_normal():
    action = derive_risk_action(
        _row(opportunity_state="core_dca"),
        _pos(weight=0.05, band_high=0.30),
    )
    assert action == "none"
