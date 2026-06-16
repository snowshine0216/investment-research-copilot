from __future__ import annotations
import datetime as _dt
from irc.monitor.eval.structural import (
    signal_consistency, citation_integrity, nav_quality, monitor_signal_health,
)

_TODAY = _dt.date(2026, 6, 16)


def _good_fund():
    return {
        "resolved": {"analysis_profile": "gold_etf", "weights": {"trend": 1.0},
                     "bands": {"buy": 0.1, "sell": -0.1}, "minimum_confidence": 0.5},
        "nav": {"as_of_date": "2026-06-16", "latest_unit_nav": 2.0, "nav_acc": 2.5,
                "acc_series": [["2026-06-15", 2.4], ["2026-06-16", 2.5]],
                "obs_count": 2, "max_gap_days": 1},
        "evidence_pool": [{"citation_id": "aaaa000000000000"}],
        "factor_scores": [{"name": "trend", "value": 0.3, "eligible": True, "reason": "", "confidence": 1.0}],
        "signal": {"status": "ok", "bias": "ADD_BIAS", "composite": 0.3, "signal_confidence": 1.0,
                   "available_weight": 1.0, "present_families": ["price-momentum"],
                   "contributions": [{"name": "trend", "renorm_weight": 1.0, "value": 0.3,
                                      "contribution": 0.3, "confidence": 1.0}],
                   "divergence_codes": []},
        "impacts": {"macro": [{"key": "gold", "citation_ids": ["aaaa000000000000"]}], "constituent": []},
        "narrative": {"status": "ok", "price_action": [{"claim": "x", "citation_ids": ["aaaa000000000000"]}],
                      "signal_rationale": [], "risk": []},
    }


def test_signal_consistency_pass_on_good_fund():
    assert signal_consistency(_good_fund()).status == "PASS"


def test_signal_consistency_fail_when_composite_diverges_from_contributions():
    t = _good_fund()
    t["signal"]["composite"] = 0.9   # != Σcontribution (0.3)
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_renorm_weights_not_unit():
    t = _good_fund()
    t["signal"]["contributions"][0]["renorm_weight"] = 0.5  # Σ != 1
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_bias_present_but_status_not_ok():
    t = _good_fund()
    t["signal"]["status"] = "low_confidence"   # bias must be None when status != ok
    assert signal_consistency(t).status == "FAIL"


def test_citation_integrity_pass_when_all_ids_resolve():
    assert citation_integrity(_good_fund()).status == "PASS"


def test_citation_integrity_fail_on_unresolved_narrative_id():
    t = _good_fund()
    t["narrative"]["price_action"][0]["citation_ids"] = ["dead000000000000"]
    assert citation_integrity(t).status == "FAIL"


def test_citation_integrity_resolves_constituent_against_unified_pool():
    t = _good_fund()
    t["evidence_pool"].append({"citation_id": "bbbb000000000000"})
    t["impacts"]["constituent"] = [{"key": "600519", "citation_ids": ["bbbb000000000000"]}]
    assert citation_integrity(t).status == "PASS"


def test_nav_quality_fail_when_obs_count_zero():
    t = _good_fund()
    t["nav"] = {"as_of_date": "N/A", "latest_unit_nav": 0.0, "nav_acc": None,
                "acc_series": [], "obs_count": 0, "max_gap_days": None}
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "FAIL"


def test_nav_quality_fail_when_below_minimum_observations():
    t = _good_fund()
    t["nav"]["obs_count"] = 1
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "FAIL"


def test_nav_quality_fail_when_as_of_older_than_stale_days():
    t = _good_fund()
    t["nav"]["as_of_date"] = "2000-01-01"
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "FAIL"


def test_nav_quality_warn_on_single_gap_over_five_days():
    t = _good_fund()
    t["nav"]["max_gap_days"] = 9
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_does_not_compare_na_as_of():
    t = _good_fund()
    t["nav"]["as_of_date"] = "N/A"
    t["nav"]["obs_count"] = 0
    t["nav"]["nav_acc"] = None
    # FAIL comes from obs/nav_acc, NOT from a date-parse crash
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "FAIL"


def test_monitor_signal_health_worst_wins_and_stage_name():
    t = _good_fund()
    t["nav"]["obs_count"] = 0          # nav_quality FAIL
    t["nav"]["nav_acc"] = None
    h = monitor_signal_health(t, minimum_observations=2, stale_days=7, today=_TODAY)
    assert h.stage == "monitor_signal" and h.status == "FAIL"


def test_monitor_signal_health_pass_on_good_fund():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert monitor_signal_health(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"
