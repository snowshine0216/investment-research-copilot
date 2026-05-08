from __future__ import annotations
from irc.allocation.mode_selector import select_mode


def test_build_when_account_small():
    assert select_mode(current_total_cny=10_000, monthly_new_capital_cny=1000) == "build"


def test_hybrid_at_threshold():
    assert select_mode(current_total_cny=80_000, monthly_new_capital_cny=8000) == "hybrid"


def test_steady_state_when_above_100k():
    assert select_mode(current_total_cny=200_000, monthly_new_capital_cny=10_000) == "steady_state"


def test_build_when_monthly_capital_low_even_if_balance_high():
    assert select_mode(current_total_cny=200_000, monthly_new_capital_cny=2000) == "build"
