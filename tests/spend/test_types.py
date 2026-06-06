import dataclasses
import pytest
from irc.spend.types import TaskUsage, BalanceReading, GateDecision, TaskActual, RunActuals


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


def test_task_actual_is_frozen_and_holds_per_run_means():
    a = TaskActual(task="memo_synthesis", calls=2.0,
                   avg_prompt_tokens=1500.0, avg_completion_tokens=900.0)
    assert (a.task, a.calls, a.avg_prompt_tokens, a.avg_completion_tokens) == (
        "memo_synthesis", 2.0, 1500.0, 900.0)
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        a.calls = 3.0  # type: ignore[misc]


def test_run_actuals_groups_tasks_and_search_units():
    r = RunActuals(
        tasks={"memo_synthesis": TaskActual("memo_synthesis", 1.0, 1000.0, 500.0)},
        search_units={"tavily": 4},
    )
    assert r.tasks["memo_synthesis"].calls == 1.0
    assert r.search_units["tavily"] == 4
