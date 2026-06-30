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


def test_watchdog_kills_the_whole_process_group_not_just_pid() -> None:
    """The backgrounded command spawns a grandchild; after the watchdog fires,
    the grandchild PID is gone — proving the negative-PID group kill (not a
    single-PID kill) took down the subtree (spec §2, §6.1)."""
    # The inner command writes its grandchild's PID to a file, then waits on it.
    # `bash -c 'sleep 30 & echo $! > PID; wait'` — the `sleep 30` is the grandchild.
    with_grandchild = (
        "tmp=$(mktemp); "
        "IRC_WATCHDOG_POLL=0.2 run_with_watchdog 1 "
        "bash -c 'sleep 30 & echo \\$! > \"$tmp\"; wait'; "
        'rc=$?; '
        "gpid=$(cat \"$tmp\"); "
        'echo "rc=$rc"; '
        # After the group kill the grandchild must be gone: kill -0 fails.
        'if kill -0 "$gpid" 2>/dev/null; then echo "GRANDCHILD_ALIVE"; '
        'else echo "GRANDCHILD_GONE"; fi; '
        'rm -f "$tmp"'
    )
    proc = _bash(with_grandchild, timeout=12.0)
    assert proc.returncode == 0, proc.stderr
    assert "rc=124" in proc.stdout, proc.stdout
    assert "GRANDCHILD_GONE" in proc.stdout, (
        f"process-group kill failed — grandchild survived. stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}"
    )


def test_acquire_lock_first_acquire_succeeds_and_writes_pid(tmp_path: Path) -> None:
    """First acquire returns 0, creates the lock dir, and writes $$ to pid."""
    lock = tmp_path / ".monitor.lock"
    proc = _bash(f'acquire_lock "{lock}"; echo "rc=$?"; cat "{lock}/pid"')
    assert proc.returncode == 0, proc.stderr
    assert "rc=0" in proc.stdout, proc.stdout
    assert lock.is_dir(), "lock dir must exist after acquire"
    pid = (lock / "pid").read_text(encoding="utf-8").strip()
    assert pid.isdigit() and int(pid) > 0, f"pid file must hold a numeric pid, got {pid!r}"


def test_acquire_lock_held_by_live_holder_returns_nonzero(tmp_path: Path) -> None:
    """A second acquire while the dir is held by a LIVE pid returns non-zero (skip)."""
    lock = tmp_path / ".monitor.lock"
    lock.mkdir()
    # $$ of THIS python process is alive for the duration of the bash call.
    import os
    (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
    proc = _bash(f'acquire_lock "{lock}" && echo ACQUIRED || echo SKIPPED')
    assert proc.returncode == 0, proc.stderr
    assert "SKIPPED" in proc.stdout, proc.stdout
    assert "ACQUIRED" not in proc.stdout, proc.stdout


def test_acquire_lock_reclaims_dead_holder(tmp_path: Path) -> None:
    """A lock dir holding a DEAD pid is reclaimed; acquire returns 0."""
    lock = tmp_path / ".snapshot.lock"
    lock.mkdir()
    # PID 2999999 is overwhelmingly unlikely to be alive on macOS (max pid ~99998).
    (lock / "pid").write_text("2999999", encoding="utf-8")
    proc = _bash(f'acquire_lock "{lock}" && echo ACQUIRED || echo SKIPPED')
    assert proc.returncode == 0, proc.stderr
    assert "ACQUIRED" in proc.stdout, proc.stdout
