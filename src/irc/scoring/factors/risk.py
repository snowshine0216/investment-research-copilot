from __future__ import annotations

from irc.scoring.factors.valuation_cost import FactorScore


def _dd_score(dd: float) -> float:
    if dd <= 0.10:
        return 100.0
    if dd <= 0.30:
        return 100 - (dd - 0.10) / 0.20 * 70
    return max(0.0, 30 - (dd - 0.30) * 100)


def _vol_score(vol: float) -> float:
    if vol <= 0.10:
        return 100.0
    if vol <= 0.30:
        return 100 - (vol - 0.10) / 0.20 * 60
    return max(0.0, 40 - (vol - 0.30) * 100)


def _capture_score(c: float) -> float:
    """Capture < 1 (defensive) → high score."""
    if c <= 0.6:
        return 100.0
    if c <= 1.0:
        return 100 - (c - 0.6) / 0.4 * 40
    if c <= 1.5:
        return 60 - (c - 1.0) / 0.5 * 40
    return 0.0


def score_risk(
    drawdown_3y: float,
    vol_1y: float,
    downside_capture: float,
    raw_refs: tuple[str, ...],
) -> FactorScore:
    components = {
        "drawdown": _dd_score(drawdown_3y),
        "vol": _vol_score(vol_1y),
        "downside_capture": _capture_score(downside_capture),
    }
    score = (
        0.5 * components["drawdown"]
        + 0.25 * components["vol"]
        + 0.25 * components["downside_capture"]
    )
    return FactorScore(
        score=max(0.0, min(100.0, score)),
        raw_refs=raw_refs,
        components=components,
    )
