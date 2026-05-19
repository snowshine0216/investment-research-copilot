"""Equity earnings-yield vs real-rate anchor (item 007, 2026-05-19).

Adversarial review §B3: percentile-only valuation systematically tells a
long-horizon DCA investor to underweight a multi-year bull (1995-2000
lesson). Earnings-yield - real-rate is the second-signal sanity anchor.
"""
from __future__ import annotations

import pytest

from irc.opportunity.states import (
    classify_valuation,
    expected_real_return_positive,
)
from irc.opportunity.types import OpportunityInput


def _equity(**kwargs) -> OpportunityInput:
    base = dict(
        instrument_id="017641",
        asset_class="us_etf",
        market="US",
    )
    base.update(kwargs)
    return OpportunityInput(**base)


def test_positive_real_return_signal() -> None:
    inp = _equity(earnings_yield=0.045, real_yield_10y=0.020)
    assert expected_real_return_positive(inp) is True


def test_negative_real_return_signal() -> None:
    inp = _equity(earnings_yield=0.025, real_yield_10y=0.030)
    assert expected_real_return_positive(inp) is False


def test_zero_difference_is_not_positive() -> None:
    inp = _equity(earnings_yield=0.030, real_yield_10y=0.030)
    assert expected_real_return_positive(inp) is False


def test_missing_input_returns_none() -> None:
    assert expected_real_return_positive(_equity(earnings_yield=0.04)) is None
    assert expected_real_return_positive(_equity(real_yield_10y=0.02)) is None
    assert expected_real_return_positive(_equity()) is None


def test_classify_valuation_appends_positive_phrase_for_very_expensive_equity() -> None:
    inp = _equity(
        valuation_percentile_self=0.95,
        earnings_yield=0.045,
        real_yield_10y=0.020,
    )
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    assert "earnings_yield - real_yield 为正" in reason


def test_classify_valuation_appends_negative_phrase_when_signal_weak() -> None:
    inp = _equity(
        valuation_percentile_self=0.95,
        earnings_yield=0.025,
        real_yield_10y=0.030,
    )
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    assert "earnings_yield - real_yield 非正" in reason


def test_classify_valuation_does_not_append_phrase_for_fair_equity() -> None:
    """The anchor is only relevant when the percentile path says
    expensive/very_expensive — for a fair-priced equity we don't need
    the sanity caveat."""
    inp = _equity(
        valuation_percentile_self=0.50,
        earnings_yield=0.045,
        real_yield_10y=0.020,
    )
    state, reason = classify_valuation(inp)
    assert state == "fair"
    assert "earnings_yield" not in reason


def test_classify_valuation_does_not_append_phrase_for_bond_class() -> None:
    """Bonds use the yield-percentile anchor — earnings-yield is
    inapplicable. Even with the equity-side fields populated, the bond
    path must run unaffected."""
    inp = OpportunityInput(
        instrument_id="000111",
        asset_class="cn_bond_fund",
        market="CN",
        cn_bond_yield_percentile=0.05,
        earnings_yield=0.045,
        real_yield_10y=0.020,
    )
    state, reason = classify_valuation(inp)
    assert state == "very_expensive"
    assert "earnings_yield" not in reason
