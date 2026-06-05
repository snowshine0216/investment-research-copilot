import pytest


@pytest.fixture(autouse=True)
def _skip_spend_gate(monkeypatch):
    """Legacy command-orchestration tests don't exercise the spend gate — it has
    its own dedicated tests (tests/spend/, test_run_gate.py, test_gate_wiring.py).
    Bypass it here so end-to-end runner/pipeline tests don't hit live balance
    probes or missing-config errors. Gate-specific tests monkeypatch the gate
    function directly, so this flag never affects what they assert.
    """
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")
