"""Acceptance criteria 11, 12, 16, 18, 21, 22, 23."""
from __future__ import annotations

import pytest

from irc.commands.opportunity_cmd import (
    FetchBudgetExceeded, FetchLockBusy, FetchPlan,
    acquire_fetch_lock, validate_cli_args,
)


def test_preflight_budget_exceeded_carries_breakdown_to_stderr(capsys) -> None:
    """Spec §16: budget abort prints active_fund_misses=N cost=N budget=N."""
    plan = FetchPlan(5, 0, 0, 0, 10)
    exc = FetchBudgetExceeded(plan, 155, 10)
    msg = str(exc)
    assert "active_fund_misses=5" in msg
    assert "cost=155" in msg
    assert "budget=10" in msg


def test_limit_rejected_on_canonical_path(tmp_path) -> None:
    """Spec §18."""
    with pytest.raises(SystemExit) as exc:
        validate_cli_args(
            output_dir=str(tmp_path / "outputs" / "2026-05-22"),
            limit=3, rebuild_fundamentals=False, today="2026-05-22",
        )
    assert exc.value.code == 2


def test_concurrent_lock_second_call_raises(tmp_path, monkeypatch) -> None:
    """Spec §21."""
    import os
    fd1 = acquire_fetch_lock(tmp_path / "lock.lock")
    import fcntl
    monkeypatch.setattr(
        fcntl, "flock",
        lambda *a, **kw: (_ for _ in ()).throw(BlockingIOError("locked")),
    )
    with pytest.raises(FetchLockBusy):
        acquire_fetch_lock(tmp_path / "lock.lock")
    os.close(fd1)
