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
