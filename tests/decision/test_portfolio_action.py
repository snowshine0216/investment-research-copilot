from __future__ import annotations

import pytest

from irc.decision.portfolio_action import map_portfolio_action, weight_delta


def _map(**overrides):
    base = dict(
        risk_action="none",
        score_action="watch",
        allocation_selected=False,
        is_holding=False,
        blocking_reasons=(),
    )
    base.update(overrides)
    return map_portfolio_action(**base)


def test_blocked_row_is_never_an_action() -> None:
    # Precedence (a): any blocking reason short-circuits to no_trade,
    # even when a sell signal + holding would otherwise fire.
    assert _map(
        risk_action="exit_review",
        is_holding=True,
        blocking_reasons=("data_incomplete",),
    ) == "no_trade"


def test_exit_review_holding_maps_to_exit_review() -> None:
    assert _map(risk_action="exit_review", is_holding=True) == "exit_review"


def test_trim_review_holding_maps_to_trim_review() -> None:
    assert _map(risk_action="trim_review", is_holding=True) == "trim_review"


def test_review_required_holding_maps_to_review() -> None:
    # review_required is "NEVER auto-sell" -> the softer `review`, not trim/exit.
    assert _map(risk_action="review_required", is_holding=True) == "review"


def test_buy_candidate_selected_maps_to_buy() -> None:
    assert _map(
        risk_action="none",
        score_action="buy_candidate",
        allocation_selected=True,
    ) == "buy"


def test_strong_buy_candidate_selected_maps_to_buy() -> None:
    assert _map(
        score_action="strong_buy_candidate",
        allocation_selected=True,
    ) == "buy"


def test_buy_candidate_not_selected_is_no_trade() -> None:
    assert _map(score_action="buy_candidate", allocation_selected=False) == "no_trade"


def test_default_is_no_trade() -> None:
    assert _map() == "no_trade"


@pytest.mark.parametrize("risk", ["exit_review", "trim_review", "review_required"])
def test_sell_branches_require_is_holding(risk) -> None:
    # R4 / AC7: derive_risk_action can return trim/exit for a NON-holding via
    # its legacy `overweight` branch. The mapper is the enforcement locus:
    # a non-holding never gets a sell-side action.
    assert _map(risk_action=risk, is_holding=False) == "no_trade"


def test_sell_signal_wins_over_buy_when_both_present() -> None:
    # Sell-side precedence is above the buy branch.
    assert _map(
        risk_action="exit_review",
        is_holding=True,
        score_action="buy_candidate",
        allocation_selected=True,
    ) == "exit_review"


def test_weight_delta_positive_overweight() -> None:
    assert weight_delta(0.07, 0.05) == pytest.approx(0.02)


def test_weight_delta_negative_underweight() -> None:
    assert weight_delta(0.03, 0.05) == pytest.approx(-0.02)


def test_weight_delta_none_current_treated_as_zero() -> None:
    assert weight_delta(None, 0.05) == pytest.approx(-0.05)


def test_weight_delta_none_target_treated_as_zero() -> None:
    assert weight_delta(0.05, None) == pytest.approx(0.05)
