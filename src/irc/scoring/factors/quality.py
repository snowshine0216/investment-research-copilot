from __future__ import annotations

from irc.scoring.factors.valuation_cost import FactorScore


def _aum_stability_score(p: float) -> float:
    if p <= 0.05:
        return 100.0
    if p <= 0.20:
        return 100 - (p - 0.05) / 0.15 * 50
    return max(0.0, 50 - (p - 0.20) * 200)


def _tenure_score(years: float) -> float:
    if years >= 5:
        return 100.0
    return max(0.0, years / 5 * 100)


def _concentration_score(top10: float) -> float:
    """Higher concentration → lower score."""
    if top10 <= 0.20:
        return 100.0
    if top10 <= 0.50:
        return 100 - (top10 - 0.20) / 0.30 * 60
    return max(0.0, 40 - (top10 - 0.50) * 200)


def score_quality(
    aum_stability_pct: float,
    manager_tenure_years: float,
    holdings_concentration_top10: float,
    raw_refs: tuple[str, ...],
) -> FactorScore:
    components = {
        "aum_stability": _aum_stability_score(aum_stability_pct),
        "tenure": _tenure_score(manager_tenure_years),
        "concentration": _concentration_score(holdings_concentration_top10),
    }
    score = (
        0.4 * components["aum_stability"]
        + 0.3 * components["tenure"]
        + 0.3 * components["concentration"]
    )
    return FactorScore(
        score=max(0.0, min(100.0, score)),
        raw_refs=raw_refs,
        components=components,
    )
