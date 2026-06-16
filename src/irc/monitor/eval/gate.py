"""PURE eval gate (roadmap §3.5). M0 gating set = {monitor_signal} only."""
from __future__ import annotations
from irc.monitor.eval.types import GateDecision, StageHealth
from irc.monitor.types import SignalRecord

GATING_STAGES_M0 = frozenset({"monitor_signal"})
GATING_STAGES_M1 = GATING_STAGES_M0 | frozenset({"monitor_impact", "monitor_narrative"})


def apply_eval_gate(
    signal: SignalRecord, *, health: tuple[StageHealth, ...], gating_stages: frozenset[str],
) -> GateDecision:
    considered = [h for h in health if h.stage in gating_stages]
    failed = tuple(h.stage for h in considered if h.status == "FAIL")
    if failed:
        reason = "; ".join(r for h in considered if h.status == "FAIL" for r in h.reasons)
        return GateDecision(signal.fund_id, True, failed, "gated", reason or "fresh FAIL")
    if any(h.status in ("WARN", "UNKNOWN") for h in considered):
        return GateDecision(signal.fund_id, False, (), "caveated", "")
    return GateDecision(signal.fund_id, False, (), "validated", "")


def published_state(signal: SignalRecord, gate: GateDecision) -> str:
    if signal.status != "ok":
        return "NO_CALL"
    if gate.suppressed:
        return "EVAL_GATED"
    return signal.bias  # type: ignore[return-value]
