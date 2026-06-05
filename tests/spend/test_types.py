import dataclasses
import pytest
from irc.spend.types import (
    TaskUsage, UsageProfile, CostEstimate, BalanceReading, ProviderVerdict, GateDecision,
)


def test_types_are_frozen():
    u = TaskUsage(task="memo_synthesis", avg_calls_per_run=1, avg_prompt_tokens=10,
                  avg_completion_tokens=5, samples=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        u.samples = 9  # type: ignore[misc]


def test_balance_reading_allows_unknown_amount():
    r = BalanceReading(provider="jina", currency="tokens", amount=None,
                       available=False, source="probe_failed")
    assert r.amount is None


def test_gate_decision_groups():
    d = GateDecision(blocked=(), warnings=(), ok=())
    assert d.blocked == () and d.warnings == () and d.ok == ()
