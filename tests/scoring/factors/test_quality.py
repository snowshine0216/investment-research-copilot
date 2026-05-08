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


def test_aum_stability_mid_tier_interpolates() -> None:
    # 0.05 < p <= 0.20: p=0.12 → 100 - (0.07/0.15)*50 ≈ 76.7
    s = score_quality(aum_stability_pct=0.12, manager_tenure_years=5,
                      holdings_concentration_top10=0.20, raw_refs=("r",))
    assert 65 <= s.components["aum_stability"] <= 90


def test_short_tenure_scores_proportionally() -> None:
    # years=2.5 → 2.5/5*100 = 50
    s = score_quality(aum_stability_pct=0.05, manager_tenure_years=2.5,
                      holdings_concentration_top10=0.20, raw_refs=("r",))
    assert s.components["tenure"] == 50.0


def test_concentration_mid_tier_interpolates() -> None:
    # 0.20 < top10 <= 0.50: top10=0.35 → 100 - (0.15/0.30)*60 = 70
    s = score_quality(aum_stability_pct=0.05, manager_tenure_years=8,
                      holdings_concentration_top10=0.35, raw_refs=("r",))
    assert 60 <= s.components["concentration"] <= 80


def test_high_concentration_scores_low() -> None:
    # top10 > 0.50: top10=0.80 → max(0, 40 - 0.30*200) = max(0, -20) = 0
    s = score_quality(aum_stability_pct=0.05, manager_tenure_years=8,
                      holdings_concentration_top10=0.80, raw_refs=("r",))
    assert s.components["concentration"] == 0.0
