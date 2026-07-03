from __future__ import annotations
from irc.monitor.eval.gate import (
    GATING_STAGES_M0, GATING_STAGES_M1, RUN_GLOBAL_STAGES, apply_eval_gate,
    published_state,
)
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _signal(status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id="008986", status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def test_gating_stages_m0_is_monitor_signal_only():
    assert GATING_STAGES_M0 == frozenset({"monitor_signal"})


def test_fresh_fail_suppresses_and_badge_gated():
    h = (StageHealth("monitor_signal", "FAIL", ("nav_quality FAIL",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is True and g.badge == "gated"
    assert g.failed_stages == ("monitor_signal",)


def test_warn_is_caveated_not_suppressed():
    h = (StageHealth("monitor_signal", "WARN", ("gap",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "caveated"


def test_unknown_is_caveated():
    h = (StageHealth("monitor_signal", "UNKNOWN", ("stale",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "caveated"


def test_all_pass_is_validated():
    h = (StageHealth("monitor_signal", "PASS", ()),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "validated"


def test_non_gating_stage_is_ignored():
    h = (StageHealth("monitor_impact", "FAIL", ("x",)),)  # not in GATING_STAGES_M0
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is False and g.badge == "validated"


def test_published_state_no_call_when_status_not_ok():
    g = apply_eval_gate(_signal(status="low_confidence", bias=None),
                        health=(StageHealth("monitor_signal", "PASS", ()),),
                        gating_stages=GATING_STAGES_M0)
    assert published_state(_signal(status="low_confidence", bias=None), g) == "NO_CALL"


def test_published_state_no_call_precedence_over_eval_gated():
    # status != ok AND suppressed → NO_CALL wins (can't gate a call never made)
    h = (StageHealth("monitor_signal", "FAIL", ("x",)),)
    sig = _signal(status="insufficient_evidence", bias=None)
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert g.suppressed is True
    assert published_state(sig, g) == "NO_CALL"


def test_published_state_eval_gated_when_suppressed():
    h = (StageHealth("monitor_signal", "FAIL", ("x",)),)
    sig = _signal()
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert published_state(sig, g) == "EVAL_GATED"


def test_published_state_is_bias_when_validated():
    h = (StageHealth("monitor_signal", "PASS", ()),)
    sig = _signal(bias="REDUCE_BIAS")
    g = apply_eval_gate(sig, health=h, gating_stages=GATING_STAGES_M0)
    assert published_state(sig, g) == "REDUCE_BIAS"


# ── report v4 item 001: RUN_GLOBAL_STAGES literal + caveat-reason assembly ────


def test_run_global_stages_is_explicit_literal_matching_m1_minus_m0():
    # RD-2 guard: the pin only has teeth against a LITERAL definition. If a
    # future per-fund gating stage joins GATING_STAGES_M1, this breaks loudly
    # and forces a conscious run-global-vs-fund-specific classification.
    assert RUN_GLOBAL_STAGES == frozenset({"monitor_impact", "monitor_narrative"})
    assert RUN_GLOBAL_STAGES == GATING_STAGES_M1 - GATING_STAGES_M0


def test_caveated_reason_unknown_stale_with_age_matches_p1_verbatim():
    h = (StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)),
         StageHealth("monitor_narrative", "UNKNOWN", ("stale, 16d",)))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.badge == "caveated" and g.suppressed is False
    assert g.reason == ("monitor_impact: UNKNOWN (stale, 15d); "
                        "monitor_narrative: UNKNOWN (stale, 16d)")


def test_caveated_reason_warn_only_monitor_signal():
    h = (StageHealth("monitor_signal", "WARN", ("gap 12d",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN (gap 12d)"


def test_caveated_reason_mixed_warn_and_unknown_preserves_health_order():
    h = (StageHealth("monitor_signal", "WARN", ("missed 3 trading days", "obs<2")),
         StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)),
         StageHealth("monitor_narrative", "PASS", ()))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == ("monitor_signal: WARN (missed 3 trading days, obs<2); "
                        "monitor_impact: UNKNOWN (stale, 15d)")


def test_caveated_reason_segment_split_survives_commas_and_colons():
    # RD-7 test-shape note: reason strings may contain ", " and ": " — only
    # "; " is the segment joiner, so renderer prefix-filtering stays unambiguous.
    h = (StageHealth("monitor_signal", "WARN", ("unresolved: abcd1234, twice",)),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN (unresolved: abcd1234, twice)"
    assert "; " not in g.reason


def test_caveated_reason_omits_parenthetical_when_reasons_empty():
    h = (StageHealth("monitor_signal", "WARN", ()),)
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.reason == "monitor_signal: WARN"


def test_validated_reason_stays_empty():
    h = (StageHealth("monitor_signal", "PASS", ()),
         StageHealth("monitor_impact", "PASS", ()),
         StageHealth("monitor_narrative", "PASS", ()))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.badge == "validated" and g.reason == ""


def test_gated_fail_branch_reason_byte_identical_to_today():
    # FAIL wins over WARN/UNKNOWN and keeps the OLD assembly (raw reasons,
    # no stage prefix) — unchanged by this item.
    h = (StageHealth("monitor_signal", "FAIL", ("nav_quality FAIL",)),
         StageHealth("monitor_impact", "UNKNOWN", ("stale, 15d",)))
    g = apply_eval_gate(_signal(), health=h, gating_stages=GATING_STAGES_M1)
    assert g.suppressed is True and g.badge == "gated"
    assert g.reason == "nav_quality FAIL"
