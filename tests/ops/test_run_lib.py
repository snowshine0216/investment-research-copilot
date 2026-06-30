"""Behavioral unit tests for ops/launchd/lib-run.sh.

These source the library in a bash subprocess and call its functions directly
with stub commands. No launchctl, no install.sh. All new bash is TDD'd
(spec docs/2026-06-30-launchd-watchdog/items/001-spec.md §6.1).
"""
from __future__ import annotations

import subprocess
import textwrap
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_LIB = _REPO_ROOT / "ops" / "launchd" / "lib-run.sh"


def _bash(script: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run a bash snippet that has already sourced lib-run.sh."""
    full = f'set -uo pipefail\nsource "{_LIB}"\n{script}\n'
    return subprocess.run(
        ["bash", "-c", full],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_watchdog_returns_zero_for_fast_success() -> None:
    """A command that exits 0 well within the timeout returns 0."""
    proc = _bash('run_with_watchdog 5 true; echo "rc=$?"')
    assert proc.returncode == 0, proc.stderr
    assert "rc=0" in proc.stdout, proc.stdout


def test_watchdog_propagates_nonzero_child_rc() -> None:
    """A command that exits 7 within the timeout propagates 7, not 124/0."""
    proc = _bash('run_with_watchdog 5 bash -c "exit 7"; echo "rc=$?"')
    assert proc.returncode == 0, proc.stderr  # the snippet itself succeeds
    assert "rc=7" in proc.stdout, proc.stdout


def test_watchdog_kills_overrunning_command_and_returns_124() -> None:
    """A `sleep 5` under `run_with_watchdog 1` with a 0.2s poll is killed and
    returns 124 in ~1s (spec §6.1)."""
    start = time.monotonic()
    proc = _bash(
        'IRC_WATCHDOG_POLL=0.2 run_with_watchdog 1 sleep 5; echo "rc=$?"',
        timeout=10.0,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, proc.stderr
    assert "rc=124" in proc.stdout, proc.stdout
    assert elapsed < 8.0, f"watchdog should fire in ~1s + 5s grace, took {elapsed:.1f}s"
    assert "watchdog: timed out" in proc.stderr, proc.stderr
