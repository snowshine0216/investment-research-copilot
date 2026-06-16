from __future__ import annotations
from irc.monitor.eval.gate import apply_eval_gate, published_state, GATING_STAGES_M0
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
