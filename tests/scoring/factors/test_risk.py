from __future__ import annotations

from irc.scoring.factors.risk import score_risk


def test_low_drawdown_high_score() -> None:
    s = score_risk(drawdown_3y=0.10, vol_1y=0.10, downside_capture=0.7, raw_refs=("r",))
    assert s.score >= 70


def test_high_drawdown_low_score() -> None:
    s = score_risk(drawdown_3y=0.45, vol_1y=0.30, downside_capture=1.2, raw_refs=("r",))
    assert s.score <= 30


def test_lower_downside_capture_better() -> None:
    a = score_risk(drawdown_3y=0.20, vol_1y=0.15, downside_capture=0.7, raw_refs=("r",))
    b = score_risk(drawdown_3y=0.20, vol_1y=0.15, downside_capture=1.1, raw_refs=("r",))
    assert a.score > b.score


def test_mid_drawdown_scores_between_extremes() -> None:
    # 0.10 < dd <= 0.30 interpolation: dd=0.20 → 100 - (0.10/0.20)*70 = 65
    low = score_risk(drawdown_3y=0.05, vol_1y=0.10, downside_capture=0.7, raw_refs=("r",))
    mid = score_risk(drawdown_3y=0.20, vol_1y=0.10, downside_capture=0.7, raw_refs=("r",))
    high = score_risk(drawdown_3y=0.40, vol_1y=0.10, downside_capture=0.7, raw_refs=("r",))
    assert high.score < mid.score < low.score


def test_very_high_vol_scores_near_zero() -> None:
    # vol > 0.30: vol=0.50 → max(0, 40 - 20) = 20
    s = score_risk(drawdown_3y=0.05, vol_1y=0.50, downside_capture=0.7, raw_refs=("r",))
    assert s.components["vol"] <= 25.0


def test_very_low_downside_capture_scores_max() -> None:
    # c <= 0.6 → 100
    s = score_risk(drawdown_3y=0.05, vol_1y=0.05, downside_capture=0.5, raw_refs=("r",))
    assert s.components["downside_capture"] == 100.0


def test_very_high_downside_capture_scores_zero() -> None:
    # c > 1.5 → 0
    s = score_risk(drawdown_3y=0.05, vol_1y=0.05, downside_capture=2.0, raw_refs=("r",))
    assert s.components["downside_capture"] == 0.0
