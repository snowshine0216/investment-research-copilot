"""PURE eval gate (roadmap §3.5). M0 gating set = {monitor_signal} only."""
from __future__ import annotations
from irc.monitor.eval.types import GateDecision, StageHealth
from irc.monitor.types import SignalRecord

GATING_STAGES_M0 = frozenset({"monitor_signal"})
GATING_STAGES_M1 = GATING_STAGES_M0 | frozenset({"monitor_impact", "monitor_narrative"})

# Run-global vs fund-specific caveat-cause classification (report v4 item 001,
# RD-2). EXPLICIT literal, deliberately NOT derived as M1 - M0: "run-global"
# means the health is resolved once per run at the edge (_suite_eval) and is
# identical for every fund — a resolution-locality property, NOT derivable from
# gating-set membership. A future per-fund gating stage added to
# GATING_STAGES_M1 must not silently classify as run-global; the equality guard
# test in tests/monitor/eval/test_gate.py breaks loudly instead.
RUN_GLOBAL_STAGES = frozenset({"monitor_impact", "monitor_narrative"})


def _caveat_reason(considered: list[StageHealth]) -> str:
    """P1 format (locked): one segment per WARN/UNKNOWN stage, in health order —
    "{stage}: {status} ({reasons joined ', '})", parens omitted on an empty
    reasons tuple, segments joined "; "."""
    segments = []
    for h in considered:
        if h.status not in ("WARN", "UNKNOWN"):
            continue
        joined = ", ".join(h.reasons)
        segments.append(f"{h.stage}: {h.status} ({joined})" if joined
                        else f"{h.stage}: {h.status}")
    return "; ".join(segments)


def apply_eval_gate(
    signal: SignalRecord, *, health: tuple[StageHealth, ...], gating_stages: frozenset[str],
) -> GateDecision:
    considered = [h for h in health if h.stage in gating_stages]
    failed = tuple(h.stage for h in considered if h.status == "FAIL")
    if failed:
        reason = "; ".join(r for h in considered if h.status == "FAIL" for r in h.reasons)
        return GateDecision(signal.fund_id, True, failed, "gated", reason or "fresh FAIL")
    if any(h.status in ("WARN", "UNKNOWN") for h in considered):
        return GateDecision(signal.fund_id, False, (), "caveated", _caveat_reason(considered))
    return GateDecision(signal.fund_id, False, (), "validated", "")


def published_state(signal: SignalRecord, gate: GateDecision) -> str:
    if signal.status != "ok":
        return "NO_CALL"
    if gate.suppressed:
        return "EVAL_GATED"
    return signal.bias  # type: ignore[return-value]
