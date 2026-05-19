"""Bond-fund valuation uses yield-percentile anchor (item 005, 2026-05-19).

Adversarial review §B1: NAV-percentile valuation on a 1-year duration
pure-bond fund is a momentum proxy with no economic interpretation. The
right anchor is the local yield curve.
"""
from __future__ import annotations

import pytest

from irc.opportunity.states import classify_bond_valuation, classify_valuation
from irc.opportunity.types import OpportunityInput


def _bond_input(**kwargs) -> OpportunityInput:
    return OpportunityInput(
        instrument_id="000111",
        asset_class="cn_bond_fund",
        market="CN",
        **kwargs,
    )


def test_bond_high_yield_percentile_is_cheap() -> None:
    state, reason = classify_bond_valuation(_bond_input(cn_bond_yield_percentile=0.85))
    assert state == "cheap"
    assert "85%" in reason


def test_bond_mid_yield_percentile_is_fair() -> None:
    state, _ = classify_bond_valuation(_bond_input(cn_bond_yield_percentile=0.50))
    assert state == "fair"


def test_bond_low_yield_percentile_is_very_expensive() -> None:
    state, reason = classify_bond_valuation(_bond_input(cn_bond_yield_percentile=0.05))
    assert state == "very_expensive"
    assert "5%" in reason


def test_bond_missing_yield_data_is_evidence_insufficient() -> None:
    state, reason = classify_bond_valuation(_bond_input())
    assert state == "evidence_insufficient"
    assert "CGB" in reason


def test_bond_yield_pct_in_between_bucket_is_expensive() -> None:
    state, _ = classify_bond_valuation(_bond_input(cn_bond_yield_percentile=0.20))
    assert state == "expensive"


def test_classify_valuation_dispatches_bond_class_to_yield_anchor() -> None:
    """classify_valuation must route cn_bond_fund through the bond
    classifier and ignore the equity NAV-percentile signal even when
    present."""
    inp = OpportunityInput(
        instrument_id="000134",
        asset_class="cn_bond_fund",
        market="CN",
        valuation_percentile_self=0.14,  # would say cheap on equity bands
        cn_bond_yield_percentile=0.05,    # but yields say bonds very expensive
    )
    state, _ = classify_valuation(inp)
    assert state == "very_expensive"


def test_classify_valuation_equity_unchanged() -> None:
    inp = OpportunityInput(
        instrument_id="017641",
        asset_class="us_etf",
        market="US",
        valuation_percentile_self=0.95,
    )
    state, _ = classify_valuation(inp)
    assert state == "very_expensive"
