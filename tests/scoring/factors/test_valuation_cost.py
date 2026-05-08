from __future__ import annotations

from irc.scoring.factors.valuation_cost import FactorScore, score_valuation_cost


def test_low_expense_ratio_scores_high() -> None:
    s = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.0, raw_refs=("ref1",))
    assert isinstance(s, FactorScore)
    assert s.score >= 80


def test_high_expense_ratio_scores_low() -> None:
    s = score_valuation_cost(expense_ratio=0.020, premium_discount_pct=0.0, raw_refs=("ref1",))
    assert s.score <= 30


def test_premium_drags_score() -> None:
    cheap = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.0, raw_refs=("r",))
    pricey = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.05, raw_refs=("r",))
    assert pricey.score < cheap.score


def test_discount_boosts_score() -> None:
    # Use expense_ratio=0.005 (scores 80) so discount can push it higher
    fair = score_valuation_cost(expense_ratio=0.005, premium_discount_pct=0.0, raw_refs=("r",))
    discounted = score_valuation_cost(expense_ratio=0.005, premium_discount_pct=-0.02, raw_refs=("r",))
    assert discounted.score > fair.score


def test_expense_score_mid_tier_low() -> None:
    # 0.001 < er <= 0.005: e.g. er=0.003 → 100 - (0.002/0.004)*20 = 90
    s = score_valuation_cost(expense_ratio=0.003, premium_discount_pct=0.0, raw_refs=("r",))
    assert 85.0 <= s.score <= 95.0


def test_expense_score_mid_tier_high() -> None:
    # 0.005 < er <= 0.015: e.g. er=0.010 → 80 - (0.005/0.010)*40 = 60
    s = score_valuation_cost(expense_ratio=0.010, premium_discount_pct=0.0, raw_refs=("r",))
    assert 55.0 <= s.score <= 65.0


def test_expense_score_above_max_returns_zero() -> None:
    # er > 0.030 → score = 0
    s = score_valuation_cost(expense_ratio=0.050, premium_discount_pct=0.0, raw_refs=("r",))
    assert s.score == 0.0


def test_premium_adjust_capped_negative() -> None:
    # pd_pct=0.10 → -0.10 * 400 = -40, capped at -20
    s = score_valuation_cost(expense_ratio=0.001, premium_discount_pct=0.10, raw_refs=("r",))
    assert s.components["premium_adjust"] == -20.0


def test_premium_adjust_capped_positive() -> None:
    # pd_pct=-0.10 → +0.10 * 400 = +40, capped at +20
    s = score_valuation_cost(expense_ratio=0.005, premium_discount_pct=-0.10, raw_refs=("r",))
    assert s.components["premium_adjust"] == 20.0
