from __future__ import annotations
from evals.scoring.metrics import (
    factor_breakdown_completeness,
    raw_ref_reachability,
    historical_sanity_rho,
    score_distribution_stability,
)


def _full_score(composite: float = 0.8) -> dict:
    factors = {k: {"value": 0.5, "raw_refs": [f"ref_{k}"]}
               for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")}
    return {"composite_score": composite, "factor_breakdown": factors}


def test_factor_breakdown_completeness_full():
    scores = [_full_score() for _ in range(3)]
    assert factor_breakdown_completeness(scores) == 1.0


def test_factor_breakdown_completeness_partial():
    score = {"factor_breakdown": {"valuation_cost": {}, "risk": {}}}
    assert abs(factor_breakdown_completeness([score]) - 2 / 5) < 1e-9


def test_factor_breakdown_completeness_empty():
    assert factor_breakdown_completeness([]) == 1.0


def test_raw_ref_reachability_all_in_index():
    scores = [_full_score()]
    index = {f"ref_{k}" for k in ("valuation_cost", "risk", "quality", "macro_fit", "thesis_news")}
    assert raw_ref_reachability(scores, index) == 1.0


def test_raw_ref_reachability_none_in_index():
    scores = [_full_score()]
    assert raw_ref_reachability(scores, set()) == 0.0


def test_raw_ref_reachability_empty_scores():
    assert raw_ref_reachability([], set()) == 1.0


def test_historical_sanity_rho_monotone():
    # Ascending scores: correlation should be positive
    scores = [{"composite_score": float(i)} for i in range(5)]
    rho = historical_sanity_rho(scores)
    assert rho > 0


def test_historical_sanity_rho_single():
    scores = [{"composite_score": 0.5}]
    assert historical_sanity_rho(scores) == 1.0


def test_score_distribution_stability_identical():
    a = [0.5, 0.6, 0.7]
    assert score_distribution_stability(a, a) == 0.0


def test_score_distribution_stability_shifted():
    a = [0.5, 0.5, 0.5]
    b = [0.7, 0.7, 0.7]
    assert abs(score_distribution_stability(a, b) - 0.2) < 1e-9
