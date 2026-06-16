from __future__ import annotations
import dataclasses
import pytest
from irc.monitor.eval.types import StageHealth, GateDecision, FundTraceBundle


def test_stage_health_is_frozen():
    h = StageHealth(stage="monitor_signal", status="PASS", reasons=())
    assert h.stage == "monitor_signal" and h.status == "PASS" and h.reasons == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.status = "FAIL"  # type: ignore[misc]


def test_gate_decision_is_frozen_eval_shape():
    g = GateDecision(
        fund_id="008986", suppressed=True,
        failed_stages=("monitor_signal",), badge="gated", reason="nav_quality FAIL",
    )
    assert g.fund_id == "008986" and g.suppressed is True
    assert g.failed_stages == ("monitor_signal",) and g.badge == "gated"
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.suppressed = False  # type: ignore[misc]


def test_fund_trace_bundle_defaults_for_non_lookthrough():
    b = FundTraceBundle(
        fund_id="008986", macro_impacts=(), constituent_impacts=(), constituent_pool=(),
    )
    assert b.constituent_impacts == () and b.constituent_pool == ()


def test_eval_gate_decision_is_not_spend_gate_decision():
    from irc.spend.types import GateDecision as SpendGate
    assert GateDecision is not SpendGate
    assert {f.name for f in dataclasses.fields(GateDecision)} == {
        "fund_id", "suppressed", "failed_stages", "badge", "reason",
    }
