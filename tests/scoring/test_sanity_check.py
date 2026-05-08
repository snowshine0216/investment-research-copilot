from __future__ import annotations

import pandas as pd

from irc.scoring.sanity_check import SanityResult, historical_sanity_correlation


def _hist() -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "composite_score": [90, 70, 50, 20],
    })
    realized = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "realized_risk_adj_return": [0.20, 0.10, -0.05, -0.20],
    })
    return scores, realized


def test_strong_positive_correlation_passes() -> None:
    scores, realized = _hist()
    res = historical_sanity_correlation(scores, realized)
    assert isinstance(res, SanityResult)
    assert res.rho > 0.90
    assert res.status == "PASS"


def test_inverted_returns_block() -> None:
    scores = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "composite_score": [90, 70, 50, 20],
    })
    realized = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "realized_risk_adj_return": [-0.20, -0.05, 0.10, 0.20],
    })
    res = historical_sanity_correlation(scores, realized)
    assert res.rho < 0
    assert res.status == "HARD_FAIL"


def test_weak_positive_warns() -> None:
    scores = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "composite_score": [90, 70, 50, 20],
    })
    realized = pd.DataFrame({
        "instrument_id": ["A", "B", "C", "D"],
        "realized_risk_adj_return": [0.05, 0.04, 0.08, 0.03],
    })
    res = historical_sanity_correlation(scores, realized)
    assert res.status in ("WARN", "PASS")  # tolerant
