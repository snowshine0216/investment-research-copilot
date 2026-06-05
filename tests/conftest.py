from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _skip_spend_gate(monkeypatch):
    """Bypass the preflight spend/balance gate by default in the test suite.

    The gate does live, read-only balance probes when provider keys are present
    in the environment (they are, in dev), so leaving it active would make any
    test that drives a real command runner hit the network and depend on the
    current account balance. The gate's own behaviour is covered directly by
    tests/spend/ (run_preflight, estimator, ledger, gate, probes) and by the
    dedicated wiring tests that monkeypatch the gate, so skipping it here removes
    a network dependency without losing coverage. A test that needs the live
    gate can monkeypatch.delenv("IRC_SKIP_SPEND_GATE", raising=False).
    """
    monkeypatch.setenv("IRC_SKIP_SPEND_GATE", "1")


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Empty temporary repo root with inputs/ and config/ ready to populate."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "config" / "universe").mkdir(parents=True)
    return tmp_path
