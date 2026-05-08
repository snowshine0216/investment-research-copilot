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
