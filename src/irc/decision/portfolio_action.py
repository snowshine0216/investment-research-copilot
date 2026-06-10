from __future__ import annotations

from collections.abc import Sequence

from irc.decision.models import PortfolioAction

_BUY_ACTIONS = frozenset({"buy_candidate", "strong_buy_candidate"})


def map_portfolio_action(
    *,
    risk_action: str,
    score_action: str,
    allocation_selected: bool,
    is_holding: bool,
    blocking_reasons: Sequence[str],
) -> PortfolioAction:
    """Project a discipline ``risk_action`` (+ buy signal) onto a portfolio action.

    Fixed precedence (ADR 0015 §2):
      (a) any blocking reason            -> no_trade  (a blocked row is never an action)
      (b) exit_review  AND is_holding    -> exit_review
      (c) trim_review  AND is_holding    -> trim_review
      (d) review_required AND is_holding -> review     (NEVER auto-sell)
      (e) buy-candidate AND allocation_selected -> buy
      (f) otherwise                      -> no_trade

    The ``is_holding`` gate on the three sell branches is load-bearing
    (R4): ``derive_risk_action`` can return trim/exit for a non-holding.
    """
    if blocking_reasons:
        return "no_trade"
    if is_holding:
        if risk_action == "exit_review":
            return "exit_review"
        if risk_action == "trim_review":
            return "trim_review"
        if risk_action == "review_required":
            return "review"
    if score_action in _BUY_ACTIONS and allocation_selected:
        return "buy"
    return "no_trade"


def weight_delta(current: float | None, target: float | None) -> float:
    """Return ``current - target`` in weight-fraction units (0.02 = +2pp).

    None is treated as 0.0 (a missing current weight means "not held yet";
    a missing target means "no allocation slot"). Pure subtraction — no
    accumulation — so it is deterministic across re-runs (ADR 0004 / R5).
    """
    return (current or 0.0) - (target or 0.0)
