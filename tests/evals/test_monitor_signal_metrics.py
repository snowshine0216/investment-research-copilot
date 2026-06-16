from __future__ import annotations
from evals.monitor_signal.metrics import (
    oracle_signal_match, citation_resolution, nav_completeness,
)


def _fund(*, composite=0.3, status="insufficient_evidence", bias=None, obs=2,
          pool_ids=("aaaa000000000000",), claim_ids=("aaaa000000000000",)):
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"obs_count": obs},
        "evidence_pool": [{"citation_id": c} for c in pool_ids],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True,
                           "reason": "", "confidence": 1.0}],
        "signal": {"status": status, "bias": bias, "composite": composite,
                   "signal_confidence": 1.0, "available_weight": 1.0,
                   "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [], "constituent": []},
        "narrative": {"status": "ok",
                      "price_action": [{"claim": "x", "citation_ids": list(claim_ids)}],
                      "signal_rationale": [], "risk": []},
    }


def _trace(funds):
    return {"schema_version": "1", "engine_version": "1", "run_date": "2026-06-16",
            "funds": funds}


def test_oracle_match_is_one_when_signal_faithful():
    # composite=0.3 with one trend factor of value 0.3 weight 1.0 → compute_signal reproduces it
    assert oracle_signal_match(_trace({"a": _fund()})) == 1.0


def test_oracle_match_below_one_when_composite_tampered():
    bad = _fund(composite=0.99)  # persisted composite no longer == recomputed
    assert oracle_signal_match(_trace({"a": bad})) < 1.0


def test_citation_resolution_one_when_all_resolve():
    assert citation_resolution(_trace({"a": _fund()})) == 1.0


def test_citation_resolution_below_one_on_dangling():
    bad = _fund(claim_ids=("dead000000000000",))
    assert citation_resolution(_trace({"a": bad})) < 1.0


def test_nav_completeness_fraction():
    funds = {"a": _fund(obs=2), "b": _fund(obs=0)}
    # minimum_observations default 2 → 1 of 2 complete
    assert nav_completeness(_trace(funds), minimum_observations=2) == 0.5
