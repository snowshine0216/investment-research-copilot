from __future__ import annotations

from irc.scoring.factors.quality import score_quality


def test_long_track_high_aum_high_score() -> None:
    s = score_quality(
        aum_stability_pct=0.05,
        manager_tenure_years=8,
        holdings_concentration_top10=0.20,
        raw_refs=("r",),
    )
    assert s.score >= 75


def test_unstable_aum_drags() -> None:
    a = score_quality(aum_stability_pct=0.05, manager_tenure_years=5,
                      holdings_concentration_top10=0.30, raw_refs=("r",))
    b = score_quality(aum_stability_pct=0.40, manager_tenure_years=5,
                      holdings_concentration_top10=0.30, raw_refs=("r",))
    assert a.score > b.score
