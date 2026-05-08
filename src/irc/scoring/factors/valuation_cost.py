from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorScore:
    score: float  # 0-100
    raw_refs: tuple[str, ...]
    components: dict[str, float]


def _expense_score(er: float) -> float:
    """ER 0% → 100, 0.5% → 80, 1.5% → 40, 3%+ → 0."""
    if er <= 0.001:
        return 100.0
    if er <= 0.005:
        return 100 - (er - 0.001) / 0.004 * 20
    if er <= 0.015:
        return 80 - (er - 0.005) / 0.010 * 40
    if er <= 0.030:
        return 40 - (er - 0.015) / 0.015 * 40
    return 0.0


def _premium_adjust(pd_pct: float) -> float:
    """Premium drags, discount boosts. ±5% caps at ±20 pts."""
    return max(-20.0, min(20.0, -pd_pct * 400))


def score_valuation_cost(
    expense_ratio: float,
    premium_discount_pct: float,
    raw_refs: tuple[str, ...],
) -> FactorScore:
    base = _expense_score(expense_ratio)
    adj = _premium_adjust(premium_discount_pct)
    score = max(0.0, min(100.0, base + adj))
    return FactorScore(
        score=score,
        raw_refs=raw_refs,
        components={"expense_score": base, "premium_adjust": adj},
    )
