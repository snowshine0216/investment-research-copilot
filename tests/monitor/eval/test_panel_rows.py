"""build_panel_rows builds both rows from per-fund healths (spec §5); a FAILing
deterministic_scoring health is PANEL-ONLY and never reaches the gate (§4.3, §8
step 4 guard)."""
from __future__ import annotations
from irc.monitor.eval.determinism import build_panel_rows
from irc.monitor.eval.gate import apply_eval_gate, GATING_STAGES_M1
from irc.monitor.eval.types import StageHealth
from irc.monitor.types import SignalRecord


def _sig(fid="A", status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(), divergence_codes=())


def test_build_panel_rows_returns_two_rows_named_correctly():
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ())}
    rows = build_panel_rows(sig, det, now="t")
    stages = {r.stage for r in rows}
    assert stages == {"monitor_signal", "deterministic_scoring"}
    assert all(r.ran_at == "t" for r in rows)


def test_monitor_signal_row_is_worst_of_raw_signal_health():
    # Divergence 1: the row reflects RAW signal_health worst-of, NOT a gate outcome.
    sig = {"A": StageHealth("monitor_signal", "PASS", ()),
           "B": StageHealth("monitor_signal", "WARN", ("gap 7d",))}
    det = {"A": StageHealth("deterministic_scoring", "PASS", ()),
           "B": StageHealth("deterministic_scoring", "PASS", ())}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t")}
    assert rows["monitor_signal"].status == "WARN"
    assert rows["deterministic_scoring"].status == "PASS"


def test_deterministic_row_worst_of_and_carries_reasons():
    sig = {"A": StageHealth("monitor_signal", "PASS", ())}
    det = {"A": StageHealth("deterministic_scoring", "FAIL", ("composite",))}
    rows = {r.stage: r for r in build_panel_rows(sig, det, now="t")}
    assert rows["deterministic_scoring"].status == "FAIL"
    assert any("composite" in r for r in rows["deterministic_scoring"].reasons)


def test_failing_deterministic_health_never_gates_a_bias():
    # GUARD (§8 step 4): a FAIL deterministic_scoring health is NOT in the gating set,
    # so apply_eval_gate (M1) never suppresses on it. Only monitor_signal/llm suites gate.
    det_fail = StageHealth("deterministic_scoring", "FAIL", ("composite",))
    healths = (StageHealth("monitor_signal", "PASS", ()),
               StageHealth("monitor_impact", "PASS", ()),
               StageHealth("monitor_narrative", "PASS", ()),
               det_fail)
    gate = apply_eval_gate(_sig(), health=healths, gating_stages=GATING_STAGES_M1)
    assert gate.suppressed is False
    assert "deterministic_scoring" not in GATING_STAGES_M1
    assert gate.badge == "validated"
