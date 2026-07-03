from __future__ import annotations
import datetime as _dt
from irc.monitor.eval.structural import (
    signal_consistency, citation_integrity, nav_quality, monitor_signal_health,
    flow_reconciliation, flow_coverage_health,
    valuation_reconciliation, valuation_coverage_health,
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


def test_signal_consistency_pass_when_composite_is_4dp_rounding_of_contributions():
    # signal.py rounds composite to 4dp by contract (types.py: "C, rounded 4dp"),
    # while individual contributions stay full-precision. The oracle must compare at
    # the same precision, else every real run FAILs on a ~2e-5 rounding artifact.
    t = _good_fund()
    t["signal"]["composite"] = -0.1549  # == round(Σcontribution, 4)
    t["signal"]["contributions"] = [
        {"name": "trend", "renorm_weight": 0.5625, "value": -0.773,
         "contribution": -0.43492133172990466, "confidence": 1.0},
        {"name": "macro_tilt", "renorm_weight": 0.43749999999999994, "value": 0.64,
         "contribution": 0.2799999999999999, "confidence": 0.7},
    ]
    assert signal_consistency(t).status == "PASS"


def test_signal_consistency_fail_when_renorm_weights_not_unit():
    t = _good_fund()
    t["signal"]["contributions"][0]["renorm_weight"] = 0.5  # Σ != 1
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_bias_present_but_status_not_ok():
    t = _good_fund()
    t["signal"]["status"] = "low_confidence"   # bias must be None when status != ok
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_on_nan_composite():
    # NaN composite would make `abs(nan - x) >= eps` vacuously False → silent PASS.
    t = _good_fund()
    t["signal"]["composite"] = float("nan")
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_on_inf_cancelling_contributions():
    # +inf and -inf contributions sum to NaN → the divergence check is vacuously
    # satisfied. A non-finite contribution must FAIL regardless of the composite.
    t = _good_fund()
    t["signal"]["composite"] = 0.0
    t["signal"]["contributions"] = [
        {"name": "a", "renorm_weight": 0.5, "value": 1.0, "contribution": float("inf"), "confidence": 1.0},
        {"name": "b", "renorm_weight": 0.5, "value": -1.0, "contribution": float("-inf"), "confidence": 1.0},
    ]
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_composite_key_missing():
    # A truncated signal block (no composite) must FAIL, not default to 0.0 and
    # coincidentally match a zero-summing contribution set.
    t = _good_fund()
    del t["signal"]["composite"]
    t["signal"]["contributions"] = [
        {"name": "a", "renorm_weight": 0.5, "value": 0.0, "contribution": 0.0, "confidence": 1.0},
        {"name": "b", "renorm_weight": 0.5, "value": 0.0, "contribution": 0.0, "confidence": 1.0},
    ]
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_fail_when_contribution_key_missing():
    # A contribution lacking the 'contribution' key must FAIL rather than defaulting
    # to 0.0 (which can hide a malformed/truncated trace).
    t = _good_fund()
    t["signal"]["composite"] = 0.0
    t["signal"]["contributions"] = [
        {"name": "a", "renorm_weight": 1.0, "value": 0.0, "confidence": 1.0},
    ]
    assert signal_consistency(t).status == "FAIL"


def test_signal_consistency_tolerates_tiny_renorm_float_error():
    # A ~5e-9 renorm sum artifact must not spuriously FAIL: compare Σrenorm at the
    # same 4dp precision as composite (a real off-by-1e-4 normalization still FAILs).
    t = _good_fund()
    t["signal"]["composite"] = 0.3
    t["signal"]["contributions"] = [
        {"name": "a", "renorm_weight": 0.5, "value": 0.6, "contribution": 0.3, "confidence": 1.0},
        {"name": "b", "renorm_weight": 0.500000005, "value": 0.0, "contribution": 0.0, "confidence": 1.0},
    ]
    assert signal_consistency(t).status == "PASS"


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


def test_nav_quality_pass_on_minor_holiday_gap():
    # A Labour-Day / Dragon-Boat-sized closure (~7 cal days) must NOT caveat — these
    # are routine CN market holidays, not data problems.
    t = _good_fund()
    t["nav"]["max_gap_days"] = 7
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_warn_on_single_gap_over_eight_days():
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


def test_nav_quality_warn_when_two_missing_trading_days():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 2
    t["nav"]["max_gap_days"] = 3   # fallback would PASS — calendar branch must dominate
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_pass_when_one_missing_trading_day():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 1
    t["nav"]["max_gap_days"] = 99  # fallback would WARN — calendar branch must dominate
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_pass_when_zero_missing_trading_days_over_holiday():
    # A Spring-Festival closure: big max_gap_days but zero missed open sessions.
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = 0
    t["nav"]["max_gap_days"] = 11
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


def test_nav_quality_falls_back_to_max_gap_when_calendar_absent_warn():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 9   # > _WARN_GAP_DAYS=8 → WARN
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "WARN"


def test_nav_quality_falls_back_to_max_gap_when_calendar_absent_pass():
    t = _good_fund()
    t["nav"]["as_of_date"] = _TODAY.isoformat()
    t["nav"]["missing_trading_days"] = None
    t["nav"]["max_gap_days"] = 7   # <= 8 → PASS
    assert nav_quality(t, minimum_observations=2, stale_days=7, today=_TODAY).status == "PASS"


# --- Task 4.3: flow_reconciliation oracle ---


def _trace_fund(rows, agg_value, flow_factor_value):
    return {
        "holding_metrics": {"rows": rows, "aggregate": {"value": agg_value,
                                                        "reason": None,
                                                        "covered_weight_ratio": 1.0}},
        "signal": {"contributions": [{"name": "flow", "value": flow_factor_value}]},
    }


def test_flow_reconciliation_passes_when_board_matches_factor():
    rows = [{"weight_pct": 30.0, "flow_score": 1.0},
            {"weight_pct": 10.0, "flow_score": -0.5}]
    t = _trace_fund(rows, 0.625, 0.625)   # (30*1 + 10*-0.5)/40
    assert flow_reconciliation(t).status == "PASS"


def test_flow_reconciliation_fails_on_mismatch():
    rows = [{"weight_pct": 30.0, "flow_score": 1.0}]
    t = _trace_fund(rows, 1.0, 0.5)   # factor value disagrees with board
    assert flow_reconciliation(t).status == "FAIL"


def test_flow_reconciliation_na_factor_is_pass():
    # no flow contribution (factor N/A) → nothing to reconcile → PASS.
    t = {"holding_metrics": {"rows": [], "aggregate": {"value": None}},
         "signal": {"contributions": []}}
    assert flow_reconciliation(t).status == "PASS"


# --- Task 4.3 (gap §5.E): flow_coverage_health ---


def _coverage_trace(rows, covered_weight_ratio=None, aggregate_reason=None):
    """Helper: build a minimal holding_metrics trace for coverage tests."""
    agg = {"value": 0.5, "reason": aggregate_reason}
    if covered_weight_ratio is not None:
        agg["covered_weight_ratio"] = covered_weight_ratio
    return {"holding_metrics": {"rows": rows, "aggregate": agg}}


def test_flow_coverage_health_status_always_pass():
    """Status must always be PASS — this is observability, not a gate."""
    rows = [
        {"weight_pct": 30.0, "flow_score": 0.5, "flow_reason": None,
         "pe_percentile": 0.4, "pb": 1.2, "valuation_reason": "low"},
        {"weight_pct": 20.0, "flow_score": None, "flow_reason": "flow_no_data",
         "pe_percentile": None, "pb": None, "valuation_reason": "pe_no_data"},
    ]
    h = flow_coverage_health(_coverage_trace(rows, covered_weight_ratio=0.6))
    assert h.status == "PASS"


def test_flow_coverage_health_stage_name():
    h = flow_coverage_health(_coverage_trace([]))
    assert h.stage == "flow_coverage"


def test_flow_coverage_health_flow_cover_reason_from_aggregate():
    """flow_cover comes from aggregate.covered_weight_ratio when present."""
    rows = [{"weight_pct": 50.0, "flow_score": 0.5, "flow_reason": None,
             "pe_percentile": 0.3, "pb": 1.0, "valuation_reason": "ok"}]
    h = flow_coverage_health(_coverage_trace(rows, covered_weight_ratio=0.75))
    assert any("flow_cover 0.75" in r for r in h.reasons)


def test_flow_coverage_health_pe_cover_reason():
    """pe_cover = fraction of rows with pe_percentile not None."""
    rows = [
        {"weight_pct": 40.0, "flow_score": 0.5, "flow_reason": None,
         "pe_percentile": 0.6, "pb": 1.5, "valuation_reason": "ok"},
        {"weight_pct": 60.0, "flow_score": 0.3, "flow_reason": None,
         "pe_percentile": None, "pb": 2.0, "valuation_reason": "pb_only"},
    ]
    h = flow_coverage_health(_coverage_trace(rows, covered_weight_ratio=1.0))
    assert any("pe_cover 0.5" in r for r in h.reasons)


def test_flow_coverage_health_flow_no_data_tally():
    """Count rows where flow_reason == 'flow_no_data'."""
    rows = [
        {"weight_pct": 30.0, "flow_score": None, "flow_reason": "flow_no_data",
         "pe_percentile": None, "pb": None, "valuation_reason": ""},
        {"weight_pct": 30.0, "flow_score": None, "flow_reason": "flow_no_data",
         "pe_percentile": None, "pb": None, "valuation_reason": ""},
        {"weight_pct": 40.0, "flow_score": 0.5, "flow_reason": None,
         "pe_percentile": 0.4, "pb": 1.0, "valuation_reason": "ok"},
    ]
    h = flow_coverage_health(_coverage_trace(rows, covered_weight_ratio=0.4))
    assert any("flow_no_data 2" in r for r in h.reasons)


def test_flow_coverage_health_flow_no_coverage_tally_from_aggregate_reason():
    """flow_no_coverage count is 1 when aggregate.reason == 'flow_no_coverage'."""
    rows = [{"weight_pct": 100.0, "flow_score": None, "flow_reason": "flow_no_data",
             "pe_percentile": None, "pb": None, "valuation_reason": ""}]
    h = flow_coverage_health(
        _coverage_trace(rows, covered_weight_ratio=0.0,
                        aggregate_reason="flow_no_coverage")
    )
    assert any("flow_no_coverage 1" in r for r in h.reasons)


def test_flow_coverage_health_empty_trace_is_pass_no_raise():
    """Empty/missing holding_metrics → PASS with no crash."""
    h = flow_coverage_health({})
    assert h.status == "PASS"
    h2 = flow_coverage_health({"holding_metrics": {}})
    assert h2.status == "PASS"


def test_flow_coverage_health_flow_cover_fallback_when_no_ratio_key():
    """When covered_weight_ratio absent, fall back to fraction of rows with flow_score."""
    rows = [
        {"weight_pct": 50.0, "flow_score": 1.0, "flow_reason": None,
         "pe_percentile": 0.5, "pb": 1.0, "valuation_reason": "ok"},
        {"weight_pct": 50.0, "flow_score": None, "flow_reason": "flow_no_data",
         "pe_percentile": None, "pb": None, "valuation_reason": ""},
    ]
    # covered_weight_ratio NOT in aggregate
    h = flow_coverage_health(_coverage_trace(rows, covered_weight_ratio=None))
    assert any("flow_cover 0.5" in r for r in h.reasons)


# ---- Task 4.2: valuation_reconciliation + valuation_coverage_health ----

def _trace_with_valuation(rows, factor_value):
    return {
        "signal": {"contributions": [{"name": "valuation", "value": factor_value}]},
        "holding_metrics": {"rows": rows},
    }


def test_valuation_reconciliation_passes_when_board_matches_factor():
    rows = [{"weight_pct": 50.0, "val_score": 1.0},
            {"weight_pct": 30.0, "val_score": -1.0}]
    # board = (50*1 + 30*-1)/80 = 0.25
    t = _trace_with_valuation(rows, 0.25)
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_reconciliation_clamped_row_counts_as_zero():
    rows = [{"weight_pct": 50.0, "val_score": 0.0},   # clamped
            {"weight_pct": 30.0, "val_score": 1.0}]
    # board = (50*0 + 30*1)/80 = 0.375
    t = _trace_with_valuation(rows, 0.375)
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_reconciliation_fails_on_mismatch():
    rows = [{"weight_pct": 50.0, "val_score": 1.0}]
    t = _trace_with_valuation(rows, -0.99)
    assert valuation_reconciliation(t).status == "FAIL"


def test_valuation_reconciliation_no_factor_is_pass():
    t = {"signal": {"contributions": []}, "holding_metrics": {"rows": []}}
    assert valuation_reconciliation(t).status == "PASS"


def test_valuation_coverage_health_is_informational_pass():
    rows = [{"weight_pct": 50.0, "val_score": 1.0, "industry_score": 1.0, "false_cheap": False},
            {"weight_pct": 30.0, "val_score": 0.0, "industry_score": -1.0, "false_cheap": True}]
    t = {"holding_metrics": {"rows": rows,
         "valuation_aggregate": {"value": 0.375, "reason": None, "covered_weight_ratio": 0.80}}}
    h = valuation_coverage_health(t)
    assert h.status == "PASS"
    assert any("false_cheap 1" in r for r in h.reasons)
    assert any("industry_cover" in r for r in h.reasons)


# --- Task 14: warm-up (rows-per-symbol) curve + flow_source marker ---


def test_flow_coverage_surfaces_warmup_and_source():
    t = {"holding_metrics": {
        "rows": [
            {"symbol": "600519", "flow_score": 1.0, "flow_reason": None,
             "pe_percentile": 0.3, "flow_rows": 5},
            {"symbol": "000858", "flow_score": None, "flow_reason": "flow_no_data",
             "pe_percentile": None, "flow_rows": 0},
        ],
        "aggregate": {"covered_weight_ratio": 0.6, "reason": None},
        "flow_source": "batch_today",
    }}
    from irc.monitor.eval.structural import flow_coverage_health
    h = flow_coverage_health(t)
    assert h.status == "PASS"
    joined = " ".join(h.reasons)
    assert "flow_source batch_today" in joined
    assert "flow_rows_min" in joined  # warm-up curve (min rows-per-symbol)


# ---- 004 AC-12: valuation_coverage_health board_pe_freshness reason ----


def _val_cov_trace():
    return {"holding_metrics": {
        "rows": [{"symbol": "600519", "weight_pct": 60.0, "val_score": 0.5,
                  "industry_score": 0.2, "false_cheap": False}],
        "valuation_aggregate": {"value": 0.5, "reason": None,
                                "covered_weight_ratio": 0.6},
    }}


def test_val_cov_board_pe_fresh_reason_appended():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "FRESH", "as_of": "2026-07-03", "age_td": 0})
    assert h.status == "PASS"
    assert "board_pe FRESH" in h.reasons


def test_val_cov_board_pe_stale_reason_names_age_and_date():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "STALE", "as_of": "2026-06-30", "age_td": 2})
    assert "board_pe STALE-2 (as_of 2026-06-30)" in h.reasons


def test_val_cov_board_pe_dark_reason_and_status_stays_pass():
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "DARK", "as_of": None, "age_td": None})
    assert "board_pe DARK" in h.reasons
    assert h.status == "PASS"          # panel-only, never a gate


def test_val_cov_no_kwarg_back_compat_no_board_pe_reason():
    h = valuation_coverage_health(_val_cov_trace())
    assert not any(r.startswith("board_pe") for r in h.reasons)


def test_val_cov_malformed_freshness_dict_degrades_to_no_reason():
    h = valuation_coverage_health(_val_cov_trace(), board_pe_freshness={"weird": 1})
    assert not any(r.startswith("board_pe") for r in h.reasons)


def test_val_cov_not_requested_emits_no_reason():
    """Round-1 P1 fix: the intentional _wants_board_pe gate-skip marker
    (NOT_REQUESTED) must render NOTHING — same silence as the pre-fix None path
    — so gold/QDII-only panels stay noise-free."""
    h = valuation_coverage_health(
        _val_cov_trace(),
        board_pe_freshness={"state": "NOT_REQUESTED", "as_of": None, "age_td": None})
    assert not any(r.startswith("board_pe") for r in h.reasons)
    assert h.status == "PASS"
