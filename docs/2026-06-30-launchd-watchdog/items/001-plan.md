# launchd Wrapper Watchdog + Single-Instance Lock — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a portable wall-clock watchdog and a single-instance lock to the two surviving launchd wrappers (`run-monitor.sh`, `run-fundamentals.sh`) by extracting two pure-bash functions into a shared, unit-tested `ops/launchd/lib-run.sh`.

**Architecture:** A new checked-in-verbatim bash library (`ops/launchd/lib-run.sh`) defines `acquire_lock <lock_dir>` (mkdir-atomic lock with stale-reclaim + `EXIT`-trap release) and `run_with_watchdog <timeout_secs> <cmd...>` (background the command under bash job control `set -m`, poll with `kill -0` on the `IRC_WATCHDOG_POLL` cadence using the `$SECONDS` wall-clock builtin, and on overrun escalate `TERM`→grace→`KILL` on the child's **process group** via negative-PID, returning `rc=124`). Both wrappers `source ops/launchd/lib-run.sh` **after** `cd "$REPO_ROOT"`, wrap their `irc` call in lock + watchdog, and `run-monitor.sh` additionally threads the captured `rc` into `notify-status` (monitor pages on timeout; snapshot is protective-only, no notify).

**Tech Stack:** bash (macOS-native, no GNU `timeout`/`setsid`); Python 3.12 + pytest for behavioral tests (subprocess + stub `uv`/`date`); `uv` toolchain.

**Source of truth:** `docs/2026-06-30-launchd-watchdog/items/001-spec.md` (user-authored, grill-hardened, merged). All §-references below point at that spec. Locked decisions in §1–§4 and §8 must not be relitigated.

---

## Orientation for the implementer (read once)

- This is a **git worktree**. Use only paths relative to the worktree root, or absolute paths under it. Never edit files via the main checkout.
- The two wrappers contain **install-time placeholders** `__UV_BIN__` and `__REPO_ROOT__`, substituted by `install.sh`. The library `lib-run.sh` has **NO placeholders** — it is pure logic, checked in verbatim (spec §3). Do **not** add placeholders to it.
- The wrappers run under `set -euo pipefail`. The `|| rc=$?` calling convention (spec §3.2/§8) is what keeps a non-zero child rc — including 124 — from aborting the script before `notify-status`. Preserve it exactly.
- The library is sourced **after** `cd "$REPO_ROOT"` so the relative `source ops/launchd/lib-run.sh` resolves (spec §3). Source it on the line right after the existing `cd "$REPO_ROOT"`.
- Existing test harness lives in `tests/ops/test_launchd_monitor.py`: `_make_stub` (a fake `uv`), `_template_wrapper` (substitutes `__UV_BIN__`/`__REPO_ROOT__` into a temp copy), `_make_date_stub` (fake `date` so the trading-day gate is deterministic), `_run_wrapper`, `_read_argv`, `_read_run_log`, and the constants `_GATE_OPEN = ("2026-06-10", "3")` / `_GATE_CLOSED = ("2026-06-14", "6")`. **Reuse these helpers — do not reinvent them.**
- `classify_run_outcome` already maps exit `124 → "timeout"` (`src/irc/notify/classify.py:15`) — no change needed there; this plan only has to deliver `rc=124` into `notify-status --last-exit-code`.
- macOS `bash` is 3.2. `$SECONDS`, `set -m`, `kill -0`, `kill -TERM -PID` (negative-PID process-group signal), and `trap … EXIT` all work in bash 3.2. Do not use bash-4-only constructs.

### File structure (what changes, and why)

| File | Responsibility |
|---|---|
| `ops/launchd/lib-run.sh` | **new** — the two pure functions `acquire_lock` + `run_with_watchdog`. No placeholders, no side effects on source. |
| `ops/launchd/run-monitor.sh` | source lib; `acquire_lock .monitor.lock` (after the idempotency skip); `run_with_watchdog ${IRC_MONITOR_TIMEOUT:-1800}` around `irc monitor`; `notify-status --last-exit-code "$rc"`. |
| `ops/launchd/run-fundamentals.sh` | source lib; `acquire_lock .snapshot.lock`; `run_with_watchdog ${IRC_SNAPSHOT_TIMEOUT:-3600}` around `irc monitor snapshot`; log `rc`; **no** notify. |
| `ops/launchd/README.md` | fix the false `.run.lock` claim (line ~27) → two per-wrapper locks; document both timeouts + the notify asymmetry. |
| `docs/adr/0016-local-scheduling-and-notification.md` | one-line pointer to the spec (no standalone ADR). |
| `tests/ops/test_run_lib.py` | **new** — behavioral unit tests for both functions (incl. process-group grandchild-kill + `IRC_WATCHDOG_POLL` fast path). |
| `tests/ops/test_launchd_monitor.py` | extend — timeout-kill→notify-124; lock-held→uv-never-called; watchdog-presence on both wrappers. |
| `tests/commands/test_notify_cmd.py` | extend — assert `lib-run.sh` defines both functions. |
| `CHANGELOG.md` | `[Unreleased]` entry. |
| `TODOS.md` | record this feature as the wrapper-level answer to the unbounded-network-hang follow-up. |

---

## Task 1: `lib-run.sh` — `run_with_watchdog` happy paths (return 0, propagate child rc)

Start with the watchdog because its non-timeout behavior (run a command, return its real exit status) is the simplest red→green loop and forces the library file into existence.

**Files:**
- Create: `tests/ops/test_run_lib.py`
- Create: `ops/launchd/lib-run.sh`

- [ ] **Step 1: Write the failing tests (file does not yet define the function)**

> **Plan amendment (deviation a — accepted):** The implementer wrote both `acquire_lock` and `run_with_watchdog` into `lib-run.sh` in this commit (Task 1), so Task 4's "fail first" step found `acquire_lock` already present. Same final code; only TDD ordering differs. The plan's step-by-step TDD ordering was a latent over-specification; the outcome is identical.

Create `tests/ops/test_run_lib.py` with exactly:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail for the right reason**

Run: `uv run pytest tests/ops/test_run_lib.py -q`
Expected: both tests FAIL. The bash subprocess errors with `lib-run.sh: No such file or directory` (the `source` fails) — i.e. failure is "library/function absent", not an assertion mismatch.

- [ ] **Step 3: Create `ops/launchd/lib-run.sh` with the minimal `run_with_watchdog`**

Create `ops/launchd/lib-run.sh` with exactly:

```bash
#!/bin/bash
# Shared launchd wrapper helpers — sourced by run-monitor.sh / run-fundamentals.sh
# AFTER `cd "$REPO_ROOT"` (so the relative `source ops/launchd/lib-run.sh` resolves).
#
# Pure logic, NO __UV_BIN__/__REPO_ROOT__ placeholders — checked in verbatim.
# Restores the two robustness primitives lost when run-daily.sh was deleted in the
# single-daily-12:15 schedule rework (#178). Rationale lives in
# docs/2026-06-30-launchd-watchdog/items/001-spec.md (no standalone ADR; ADR 0016
# carries a one-line pointer).

# run_with_watchdog <timeout_secs> <cmd> [args...]
#
# Background <cmd args...> under bash job control so it becomes a process-group
# leader (PGID == $!), poll it on the IRC_WATCHDOG_POLL cadence using the bash
# $SECONDS wall-clock builtin, and on overrun escalate TERM -> grace -> KILL on
# the whole PROCESS GROUP (negative PID), returning 124. `uv run irc ...` spawns
# a Python child, so a single-PID kill would orphan the worker (continued paid
# spend + a late monitor.json write); the group kill takes down uv + Python +
# grandchildren in one shot. macOS-native: no GNU timeout, no setsid.
run_with_watchdog() {
  local timeout="$1"
  shift
  set -m                       # job control: backgrounded job leads its own group
  "$@" &
  local pid=$!                 # == PGID under set -m
  set +m
  SECONDS=0                    # bash wall-clock builtin; immune to system load
  local killed=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$SECONDS" -ge "$timeout" ]; then
      echo "[$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S')] watchdog: timed out after ${timeout}s — killing process group $pid" >&2
      kill -TERM -"$pid" 2>/dev/null || true   # negative PID = whole group
      sleep 5
      kill -KILL -"$pid" 2>/dev/null || true
      killed=1
      break
    fi
    sleep "${IRC_WATCHDOG_POLL:-10}"           # kill -0 check cadence (tests: 0.2)
  done
  if [ "$killed" -eq 1 ]; then
    return 124
  fi
  local rc=0
  wait "$pid" || rc=$?
  return "$rc"
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/ops/test_run_lib.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ops/launchd/lib-run.sh tests/ops/test_run_lib.py
git commit -m "feat(launchd): run_with_watchdog happy paths (return 0, propagate child rc)"
```

---

## Task 2: `run_with_watchdog` — the timeout→124 kill path (fast via `IRC_WATCHDOG_POLL`)

**Files:**
- Modify: `tests/ops/test_run_lib.py`
- (no library change expected — Task 1's implementation already covers the kill path; this task proves it)

- [ ] **Step 1: Append the failing test**

Add to `tests/ops/test_run_lib.py`:

```python
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
```

- [ ] **Step 2: Run to verify it passes (kill path already implemented in Task 1)**

Run: `uv run pytest tests/ops/test_run_lib.py::test_watchdog_kills_overrunning_command_and_returns_124 -q`
Expected: 1 passed (in roughly 6–7s — 1s to detect overrun + the 5s TERM→KILL grace).

> If this test instead FAILS, the kill path in Task 1 is wrong (e.g. `$SECONDS` not reset, or the poll/`kill -0` loop never breaks). Fix `run_with_watchdog` in `ops/launchd/lib-run.sh` until green — do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/ops/test_run_lib.py
git commit -m "test(launchd): watchdog timeout-kill returns 124 via IRC_WATCHDOG_POLL fast path"
```

---

## Task 3: `run_with_watchdog` — process-GROUP kill (grandchild PID gone)

This is the headline correction over the old `run-daily.sh` code (spec §2): the kill must take down the whole subtree, not just `$!`.

**Files:**
- Modify: `tests/ops/test_run_lib.py`
- (proves Task 1's `kill -TERM -"$pid"` group semantics)

- [ ] **Step 1: Append the failing test**

Add to `tests/ops/test_run_lib.py`:

```python
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
```

> Note on quoting: this string is passed through Python → `bash -c "<full>"` (see `_bash`). The `\\$!` becomes `\$!` in the bash snippet so `$!` is expanded by the *inner* `bash -c '...'` (the grandchild's own shell), not the outer one. `"$tmp"` is expanded by the outer shell (the temp path is shared). Keep the escaping exactly as written.

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/ops/test_run_lib.py::test_watchdog_kills_the_whole_process_group_not_just_pid -q`
Expected: 1 passed.

> If `GRANDCHILD_ALIVE` appears, the kill is hitting only `$!`. Verify `ops/launchd/lib-run.sh` uses `kill -TERM -"$pid"` / `kill -KILL -"$pid"` (the leading `-` before `$pid` makes it a process-group signal) and that `set -m` runs *before* backgrounding the command. Do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add tests/ops/test_run_lib.py
git commit -m "test(launchd): watchdog kills the whole process group (grandchild gone)"
```

---

## Task 4: `acquire_lock` — acquire, contention-skip, stale-reclaim

**Files:**
- Modify: `tests/ops/test_run_lib.py`
- Modify: `ops/launchd/lib-run.sh`

- [ ] **Step 1: Append the failing tests**

Add to `tests/ops/test_run_lib.py`:

```python
def test_acquire_lock_first_acquire_succeeds_and_writes_pid(tmp_path: Path) -> None:
    """First acquire returns 0, creates the lock dir, and writes $$ to pid."""
    lock = tmp_path / ".monitor.lock"
    # Plan amendment (deviation c — correct adjustment): reads pid from bash stdout
    # (cat inside the snippet runs before the EXIT trap removes the dir) rather than
    # lock.is_dir() after subprocess exit (the trap removes the dir on exit, so
    # lock.is_dir() would always be False). Correct: pid is the last non-empty line.
    proc = _bash(f'acquire_lock "{lock}"; echo "rc=$?"; cat "{lock}/pid"')
    assert proc.returncode == 0, proc.stderr
    assert "rc=0" in proc.stdout, proc.stdout
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    pid = lines[-1].strip() if len(lines) >= 2 else ""
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
```

- [ ] **Step 2: Run to verify they fail for the right reason**

Run: `uv run pytest tests/ops/test_run_lib.py -k acquire_lock -q`
Expected: 3 FAIL — bash reports `acquire_lock: command not found` (function not yet defined). (The watchdog tests still pass.)

- [ ] **Step 3: Add `acquire_lock` to `ops/launchd/lib-run.sh`**

> **Plan amendment (deviation b — correct bug fix):** The plan used `trap 'rm -rf "$lock_dir"'` where `lock_dir` is `local` — out of scope when the trap fires after the function returns (under `set -u` → unbound variable). Implementation fixed this to a script-global `_IRC_LOCK_DIR` set before each trap install: `_IRC_LOCK_DIR="$lock_dir"; trap 'rm -rf "$_IRC_LOCK_DIR"' EXIT`. This is a CORRECT bug fix; the plan text below is amended to match.

Insert this function into `ops/launchd/lib-run.sh` **above** `run_with_watchdog` (after the file header comment):

```bash
# acquire_lock <lock_dir>
#
# Atomic single-instance lock via `mkdir` (mkdir is atomic across processes).
# On success: write $$ to <lock_dir>/pid, install an EXIT trap that removes the
# dir, return 0. On contention: if the holder pid is alive return non-zero
# (caller skips); if the holder is gone, reclaim (rm -rf + retry mkdir). bash
# traps are global, but only acquire_lock installs an EXIT trap, so there is no
# trap-stacking ambiguity. The lock prevents duplicate paid LLM spend + wasted
# concurrent work (the forward ledger reader dedups, so it is bloat-not-
# contamination). See spec §3.1 / §4.3.
acquire_lock() {
  local lock_dir="$1"
  if mkdir "$lock_dir" 2>/dev/null; then
    echo "$$" > "$lock_dir/pid"
    _IRC_LOCK_DIR="$lock_dir"
    trap 'rm -rf "$_IRC_LOCK_DIR"' EXIT
    return 0
  fi
  local holder
  holder="$(cat "$lock_dir/pid" 2>/dev/null || true)"
  if [ -n "${holder:-}" ] && kill -0 "$holder" 2>/dev/null; then
    return 1   # held by a live process — caller skips
  fi
  # Holder is gone — reclaim the stale lock and retry once.
  rm -rf "$lock_dir"
  if mkdir "$lock_dir" 2>/dev/null; then
    echo "$$" > "$lock_dir/pid"
    _IRC_LOCK_DIR="$lock_dir"
    trap 'rm -rf "$_IRC_LOCK_DIR"' EXIT
    return 0
  fi
  return 1
}
```

- [ ] **Step 4: Run to verify all library tests pass**

Run: `uv run pytest tests/ops/test_run_lib.py -q`
Expected: 6 passed (3 watchdog + 3 lock).

- [ ] **Step 5: Commit**

```bash
git add ops/launchd/lib-run.sh tests/ops/test_run_lib.py
git commit -m "feat(launchd): acquire_lock with stale-reclaim + EXIT-trap release"
```

---

## Task 5: Wire `run-monitor.sh` — source lib, lock, watchdog, notify-with-rc

The library is proven. Now wire the monitor wrapper. Per spec §4.1 the final order is: trading-day gate → `monitor.json` idempotency skip → **lock** → **watchdog around `irc monitor`** → notify-status with `rc` → `exit "$rc"`.

**Files:**
- Modify: `tests/ops/test_launchd_monitor.py`
- Modify: `ops/launchd/run-monitor.sh:53-56`

- [ ] **Step 1: Add the timeout-kill + lock-skip integration tests**

> **Plan amendment (deviation d — clean addition):** `_template_wrapper` was extended to copy `lib-run.sh` into `tmp_path/ops/launchd/` so the relative `source ops/launchd/lib-run.sh` resolves under the test's substituted `__REPO_ROOT__`. This was a necessary infrastructure fix not anticipated by the plan.

Append to `tests/ops/test_launchd_monitor.py` (the harness helpers `_make_stub`, `_template_wrapper`, `_make_date_stub`, `_run_wrapper`, `_read_argv`, `_GATE_OPEN` already exist in this file — reuse them):

```python
# ---------------------------------------------------------------------------
# Wrapper integration: watchdog timeout-kill + single-instance lock (item 001)
# ---------------------------------------------------------------------------


def _make_sleepy_uv_stub(tmp_path: Path, monitor_sleep: int) -> tuple[Path, Path]:
    """A stub `uv` whose `irc monitor` sleeps <monitor_sleep>s (to be killed by
    the watchdog) but whose `notify-status` returns instantly with exit 0.
    Records every argv line to stub_argv.log."""
    # Plan amendment (deviation e — correct fix): removed the early `if [ "$arg" = "snapshot" ]; then exit 0; fi`
    # branch. With it, `irc monitor snapshot` returned immediately (exit 0), bypassing the watchdog
    # entirely and causing `test_fundamentals_wrapper_watchdog_kills_and_exits_124_without_notify` to fail.
    # The stub must sleep for ALL non-notify-status calls so the watchdog has something to kill.
    argv_log = tmp_path / "stub_argv.log"
    stub = tmp_path / "uv"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            echo "$@" >> {argv_log}
            for arg in "$@"; do
              if [ "$arg" = "notify-status" ]; then exit 0; fi
            done
            # irc monitor / irc monitor snapshot: sleep so the watchdog has
            # something to kill.
            sleep {monitor_sleep}
            exit 0
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub, argv_log


def test_monitor_wrapper_watchdog_kills_and_notifies_124(tmp_path: Path) -> None:
    """A monitor run that overruns IRC_MONITOR_TIMEOUT is killed by the watchdog,
    and the wrapper calls notify-status with --last-exit-code 124 (spec §4.1)."""
    stub, argv_log = _make_sleepy_uv_stub(tmp_path, monitor_sleep=30)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    result = _run_wrapper(
        wrapper,
        {
            "PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}",
            "IRC_MONITOR_TIMEOUT": "1",
            "IRC_WATCHDOG_POLL": "0.2",
        },
    )
    assert result.returncode == 124, (
        f"wrapper must exit 124 on watchdog kill; got {result.returncode}. "
        f"log:\n{_read_run_log(tmp_path, 'run-monitor')}"
    )
    invocations = _read_argv(argv_log)
    notify = [ln for ln in invocations if "notify-status" in ln]
    assert notify, f"notify-status must be called after a timeout. argv: {invocations}"
    assert any("--last-exit-code 124" in ln for ln in notify), (
        f"notify-status must receive --last-exit-code 124. notify calls: {notify}"
    )


def test_monitor_wrapper_skips_when_lock_held(tmp_path: Path) -> None:
    """When .monitor.lock is held by a LIVE pid, the wrapper skips (exit 0) and
    never calls `uv run irc monitor` (spec §4.1: silent skip-on-contention)."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-monitor.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN)
    # Pre-create the lock dir held by THIS process (alive for the call duration).
    lock = tmp_path / "outputs" / "_logs" / ".monitor.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
    result = _run_wrapper(wrapper, {"PATH": f"{date_bin}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0, result.stderr
    invocations = _read_argv(argv_log)
    assert not any(
        "monitor" in ln and "notify-status" not in ln and "snapshot" not in ln
        for ln in invocations
    ), f"uv must NOT be called for `irc monitor` while the lock is held. argv: {invocations}"
```

- [ ] **Step 2: Run to verify both fail for the right reason**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k "watchdog_kills_and_notifies_124 or skips_when_lock_held" -q`
Expected: both FAIL.
- `watchdog_kills_and_notifies_124`: the *current* wrapper has no watchdog, so the stub's `sleep 30` runs to completion and `_run_wrapper`'s `timeout=30` trips → the subprocess is killed and the assertion on rc=124 never holds (likely a `subprocess.TimeoutExpired` or rc≠124). Either way: not green.
- `skips_when_lock_held`: the current wrapper has no lock, so it runs `irc monitor` despite the held lock → the "uv must NOT be called for `irc monitor`" assertion fails.

- [ ] **Step 3: Wire the watchdog + lock into `ops/launchd/run-monitor.sh`**

First, add the `source` line. In `ops/launchd/run-monitor.sh`, find:

```bash
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs
```

and change it to:

```bash
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs
```

Then replace the tail of the file. Find the existing final block:

```bash
rc=0
"$UV_BIN" run irc monitor || rc=$?
"$UV_BIN" run irc notify-status --run-kind monitor --last-exit-code "$rc" || true
exit "$rc"
```

and replace it with:

```bash
# Single-instance lock: prevent a manual run and the scheduled fire (or any two
# fires) from overlapping — chiefly to avoid duplicate paid LLM spend + wasted
# concurrent work. Sits AFTER the idempotency skip (no point locking a day we are
# skipping). Skip-on-contention is SILENT (exit 0, no notify) — consistent with
# the weekend / holiday / idempotency skips; a skip is not a failure. Released
# via the EXIT trap acquire_lock installs. See lib-run.sh / spec §4.1 / §4.3.
acquire_lock "outputs/_logs/.monitor.lock" || {
  echo "[$TODAY] another monitor run in progress — skipping."
  exit 0
}

# Watchdog: bound the run at IRC_MONITOR_TIMEOUT (default 1800s / 30 min). On
# overrun the whole process group is killed (TERM -> grace -> KILL) and rc=124,
# which notify-status maps to "timeout". The `|| rc=$?` keeps a non-zero child
# rc (incl. 124) from aborting the script under `set -e` before notify runs.
rc=0
run_with_watchdog "${IRC_MONITOR_TIMEOUT:-1800}" "$UV_BIN" run irc monitor || rc=$?
"$UV_BIN" run irc notify-status --run-kind monitor --last-exit-code "$rc" || true
exit "$rc"
```

- [ ] **Step 4: Run the two new tests to verify they pass**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k "watchdog_kills_and_notifies_124 or skips_when_lock_held" -q`
Expected: 2 passed.

- [ ] **Step 5: Run the whole monitor test file to confirm no regression**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -q`
Expected: all passing (the pre-existing weekend/idempotency/notify/partial-output tests still green — the lock sits *after* those gates, so weekend/holiday/idempotency skips short-circuit before `acquire_lock` and never touch it).

- [ ] **Step 6: bash -n the wrapper**

Run: `bash -n ops/launchd/run-monitor.sh`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add ops/launchd/run-monitor.sh tests/ops/test_launchd_monitor.py
git commit -m "feat(launchd): wire watchdog + lock into run-monitor.sh; timeout pages 124"
```

---

## Task 6: Wire `run-fundamentals.sh` — source lib, lock, watchdog, NO notify

Per spec §4.2: lock → watchdog around `irc monitor snapshot` (`IRC_SNAPSHOT_TIMEOUT` default 3600) → log `rc` → `exit "$rc"`. **No `notify-status`** (protective-only — spec §4.2 asymmetry).

**Files:**
- Modify: `tests/ops/test_launchd_monitor.py`
- Modify: `ops/launchd/run-fundamentals.sh:20-21`

- [ ] **Step 1: Add the snapshot watchdog + lock-skip tests**

Append to `tests/ops/test_launchd_monitor.py`:

```python
def test_fundamentals_wrapper_watchdog_kills_and_exits_124_without_notify(
    tmp_path: Path,
) -> None:
    """A snapshot run that overruns IRC_SNAPSHOT_TIMEOUT is killed (exit 124),
    and NO notify-status is called (protective-only asymmetry, spec §4.2)."""
    stub, argv_log = _make_sleepy_uv_stub(tmp_path, monitor_sleep=30)
    wrapper = _template_wrapper(_OPS / "run-fundamentals.sh", tmp_path, stub)
    result = _run_wrapper(
        wrapper,
        {"IRC_SNAPSHOT_TIMEOUT": "1", "IRC_WATCHDOG_POLL": "0.2"},
    )
    assert result.returncode == 124, (
        f"snapshot wrapper must exit 124 on watchdog kill; got {result.returncode}. "
        f"log:\n{_read_run_log(tmp_path, 'run-fundamentals')}"
    )
    invocations = _read_argv(argv_log)
    assert not any("notify-status" in ln for ln in invocations), (
        f"run-fundamentals.sh must NOT call notify-status (protective-only). argv: {invocations}"
    )


def test_fundamentals_wrapper_skips_when_snapshot_lock_held(tmp_path: Path) -> None:
    """When .snapshot.lock is held by a LIVE pid, the wrapper skips (exit 0) and
    never runs the snapshot (spec §4.2 / §4.3 per-wrapper locks)."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    wrapper = _template_wrapper(_OPS / "run-fundamentals.sh", tmp_path, stub)
    lock = tmp_path / "outputs" / "_logs" / ".snapshot.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()), encoding="utf-8")
    result = _run_wrapper(wrapper)
    assert result.returncode == 0, result.stderr
    assert not any("snapshot" in ln for ln in _read_argv(argv_log)), (
        f"snapshot must NOT run while .snapshot.lock is held. argv: {_read_argv(argv_log)}"
    )
```

- [ ] **Step 2: Run to verify both fail**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k "fundamentals_wrapper_watchdog or skips_when_snapshot_lock_held" -q`
Expected: both FAIL — the current `run-fundamentals.sh` runs `irc monitor snapshot` unbounded (no watchdog → `sleep 30` overruns the 30s subprocess timeout) and has no lock (snapshot runs despite the held lock).

- [ ] **Step 3: Wire the watchdog + lock into `ops/launchd/run-fundamentals.sh`**

In `ops/launchd/run-fundamentals.sh`, find:

```bash
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs
```

and change it to:

```bash
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs
```

Then find the existing final two lines:

```bash
echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] quarterly monitor snapshot refresh"
"$UV_BIN" run irc monitor snapshot
```

and replace them with:

```bash
echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] quarterly monitor snapshot refresh"

# Single-instance lock (.snapshot.lock — per-wrapper, NOT shared with the monitor
# lock: a shared lock would let an overrunning 06:00 snapshot false-skip the 12:15
# monitor for a whole day; see spec §4.3). Silent skip-on-contention.
acquire_lock "outputs/_logs/.snapshot.lock" || {
  echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] another snapshot run in progress — skipping."
  exit 0
}

# Watchdog only — PROTECTIVE-ONLY: a snapshot timeout is logged loudly (the rc=124
# watchdog line in this per-run log) but does NOT page. The snapshot has no single
# completion-sentinel artifact for a notify run-kind to test, and a killed snapshot
# is already surfaced indirectly (the next daily monitor brief degrades affected
# factors to N/A). The watchdog's value here is purely killing a stuck constituent
# socket so the process does not linger and the lock is freed. See spec §4.2.
rc=0
run_with_watchdog "${IRC_SNAPSHOT_TIMEOUT:-3600}" "$UV_BIN" run irc monitor snapshot || rc=$?
echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] snapshot finished rc=$rc"
exit "$rc"
```

- [ ] **Step 4: Run the two new tests to verify they pass**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k "fundamentals_wrapper_watchdog or skips_when_snapshot_lock_held" -q`
Expected: 2 passed.

- [ ] **Step 5: Run the whole monitor test file**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -q`
Expected: all passing (incl. the pre-existing `test_run_fundamentals_sh_calls_irc_monitor_snapshot` — `irc monitor snapshot` still appears verbatim in the wrapper, now as the watchdog's args).

- [ ] **Step 6: bash -n the wrapper**

Run: `bash -n ops/launchd/run-fundamentals.sh`
Expected: no output, exit 0.

- [ ] **Step 7: Commit**

```bash
git add ops/launchd/run-fundamentals.sh tests/ops/test_launchd_monitor.py
git commit -m "feat(launchd): wire watchdog + lock into run-fundamentals.sh (protective-only, no notify)"
```

---

## Task 7: Restored watchdog-presence assertions on both wrappers

Spec §6.2 requires restoring a watchdog-presence content assertion — replacing the one deleted in #179 — now backed by a real implementation: assert both wrappers source `lib-run.sh` and pass an `IRC_*_TIMEOUT`-defaulted ceiling into `run_with_watchdog`.

**Files:**
- Modify: `tests/ops/test_launchd_monitor.py`

- [ ] **Step 1: Add the presence tests**

Append to `tests/ops/test_launchd_monitor.py`:

```python
def test_both_wrappers_source_lib_run() -> None:
    """Both surviving wrappers must source the shared library (spec §3 / §6.2)."""
    for name in ("run-monitor.sh", "run-fundamentals.sh"):
        text = (_OPS / name).read_text(encoding="utf-8")
        assert "source ops/launchd/lib-run.sh" in text, (
            f"{name} must `source ops/launchd/lib-run.sh` (after cd REPO_ROOT)"
        )


def test_monitor_wrapper_invokes_watchdog_with_timeout_default() -> None:
    """run-monitor.sh must call run_with_watchdog with an IRC_MONITOR_TIMEOUT
    default of 1800 around `irc monitor` (spec §4.1 / §6.2)."""
    text = (_OPS / "run-monitor.sh").read_text(encoding="utf-8")
    assert 'run_with_watchdog "${IRC_MONITOR_TIMEOUT:-1800}"' in text, (
        "run-monitor.sh must wrap irc monitor in run_with_watchdog with a 1800s default"
    )
    assert "run irc monitor" in text


def test_fundamentals_wrapper_invokes_watchdog_with_timeout_default() -> None:
    """run-fundamentals.sh must call run_with_watchdog with an IRC_SNAPSHOT_TIMEOUT
    default of 3600 around `irc monitor snapshot` (spec §4.2 / §6.2)."""
    text = (_OPS / "run-fundamentals.sh").read_text(encoding="utf-8")
    assert 'run_with_watchdog "${IRC_SNAPSHOT_TIMEOUT:-3600}"' in text, (
        "run-fundamentals.sh must wrap irc monitor snapshot in run_with_watchdog "
        "with a 3600s default"
    )
    assert "run irc monitor snapshot" in text


def test_fundamentals_wrapper_has_no_notify_status() -> None:
    """run-fundamentals.sh must NOT call notify-status (protective-only, spec §4.2)."""
    text = (_OPS / "run-fundamentals.sh").read_text(encoding="utf-8")
    assert "notify-status" not in text, (
        "run-fundamentals.sh is protective-only — it must not page via notify-status"
    )
```

- [ ] **Step 2: Run to verify they pass (Tasks 5–6 already implemented the wiring)**

Run: `uv run pytest tests/ops/test_launchd_monitor.py -k "source_lib_run or invokes_watchdog or has_no_notify_status" -q`
Expected: 4 passed.

> These are content assertions over code committed in Tasks 5–6, so they go green immediately. If any fails, the wrapper text does not match the strings above — reconcile the wrapper to the exact strings in Tasks 5/6 (do not loosen the assertion).

- [ ] **Step 3: Commit**

```bash
git add tests/ops/test_launchd_monitor.py
git commit -m "test(launchd): restore watchdog-presence assertions on both wrappers"
```

---

## Task 8: `test_notify_cmd.py` — assert `lib-run.sh` defines both functions

Spec §6.3: the `bash -n` glob in this file already lints the new `lib-run.sh` automatically; add a focused assertion that `lib-run.sh` defines both functions.

**Files:**
- Modify: `tests/commands/test_notify_cmd.py`

- [ ] **Step 1: Add the assertion test**

Append to `tests/commands/test_notify_cmd.py`:

```python
def test_lib_run_sh_defines_both_functions():
    """spec §6.3: ops/launchd/lib-run.sh must define both acquire_lock and
    run_with_watchdog (the entire public interface, spec §3)."""
    text = (_OPS / "lib-run.sh").read_text(encoding="utf-8")
    assert "acquire_lock()" in text, "lib-run.sh must define acquire_lock()"
    assert "run_with_watchdog()" in text, "lib-run.sh must define run_with_watchdog()"
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/commands/test_notify_cmd.py::test_lib_run_sh_defines_both_functions -q`
Expected: 1 passed.

- [ ] **Step 3: Confirm the existing `bash -n` glob now lints `lib-run.sh` too**

Run: `uv run pytest tests/commands/test_notify_cmd.py::test_all_shell_scripts_pass_bash_syntax_check -q`
Expected: 1 passed (this test globs `ops/launchd/*.sh`, so it now also syntax-checks `lib-run.sh`).

- [ ] **Step 4: Commit**

```bash
git add tests/commands/test_notify_cmd.py
git commit -m "test(launchd): assert lib-run.sh defines acquire_lock + run_with_watchdog"
```

---

## Task 9: Fix `README.md` — false lock claim + document timeouts + notify asymmetry

Spec §5: fix the false `.run.lock` claim at line ~27; document `IRC_MONITOR_TIMEOUT` (1800), `IRC_SNAPSHOT_TIMEOUT` (3600), the `rc=124`→"timeout" notify for monitor, and the snapshot-logs-but-does-not-page asymmetry. This is a docs task (no test), verified by content grep.

**Files:**
- Modify: `ops/launchd/README.md`

- [ ] **Step 1: Replace the false single-lock sentence**

In `ops/launchd/README.md`, find this exact line (currently line ~27):

```
A **single-instance lock** (`outputs/_logs/.run.lock`) stops two runs from overlapping.
```

and replace it with:

```
**Per-wrapper single-instance locks** stop a manual run and the scheduled fire (or
any two fires of the same job) from overlapping — chiefly to avoid duplicate paid
LLM spend and wasted concurrent work. `run-monitor.sh` holds
`outputs/_logs/.monitor.lock`; `run-fundamentals.sh` holds
`outputs/_logs/.snapshot.lock`. They are **separate on purpose**: one shared lock
would let an overrunning quarterly snapshot false-skip an entire day's monitor
brief. Each lock is an atomic `mkdir` with stale-holder reclaim and is released by
an `EXIT` trap; contention is a **silent skip** (`exit 0`, no notification — a
skip is not a failure). The lock and the `monitor.json` completion sentinel are
orthogonal: the lock is *concurrency* control, the sentinel is *completion*
detection, and both are retained.
```

- [ ] **Step 2: Add a watchdog/timeout subsection**

In `ops/launchd/README.md`, immediately **after** the `com.irc.fundamentals-quarterly` paragraph (the one ending "…degrade to N/A (surfaced, not silent).", currently ~line 38) and **before** the `## Install` heading, insert:

```markdown
## Watchdog (wall-clock timeout) + notify asymmetry

Each wrapper bounds its run with a wall-clock watchdog (shared
`ops/launchd/lib-run.sh`). The watchdog targets a **non-LLM, non-`cached_fetch`
network call with no timeout** (e.g. an AkShare `requests` call whose default
timeout is `None` can hang a half-open socket forever); LLM calls and
`cached_fetch` are already self-bounded, so the ceilings are generous, not tight.
On overrun the watchdog kills the **whole process group** (`TERM` → 5s grace →
`KILL`) — `uv run` spawns a Python child, so a single-PID kill would orphan the
worker — and reports `rc=124`.

| Wrapper | Timeout env (default) | On timeout |
|---|---|---|
| `run-monitor.sh` | `IRC_MONITOR_TIMEOUT` (1800s / 30 min) | `rc=124` → `notify-status` pages **"timeout"** (`classify` maps 124) |
| `run-fundamentals.sh` | `IRC_SNAPSHOT_TIMEOUT` (3600s / 60 min) | `rc=124` **logged loudly, does NOT page** (protective-only) |

**Why the asymmetry.** The monitor job has a single `monitor.json` completion
sentinel, so a timeout is a clean pageable outcome. The snapshot job has **no
single completion-sentinel artifact** (it refreshes constituent caches under
`data/…`), so there is nothing for a notification run-kind to test for success; a
snapshot timeout is logged in `outputs/_logs/run-fundamentals.<ts>.log` and is
already surfaced indirectly — the next daily monitor brief degrades the affected
factors to N/A within ~a day. The watchdog there is purely protective: kill the
stuck constituent socket and free the `.snapshot.lock`.
```

- [ ] **Step 3: Verify the false claim is gone and the new content is present**

Run: `grep -n "outputs/_logs/.run.lock" ops/launchd/README.md`
Expected: no output (the false single-lock reference is removed).

Run: `grep -n "IRC_MONITOR_TIMEOUT\|IRC_SNAPSHOT_TIMEOUT\|.monitor.lock\|.snapshot.lock\|protective-only" ops/launchd/README.md`
Expected: matches for all five strings.

- [ ] **Step 4: Commit**

```bash
git add ops/launchd/README.md
git commit -m "docs(launchd): fix false .run.lock claim; document timeouts + notify asymmetry"
```

---

## Task 10: ADR 0016 one-line pointer (no standalone ADR)

Spec §5: add a **one-line pointer** to this spec in ADR 0016 for the restored watchdog + per-wrapper lock — no standalone ADR (the decision is reversible ~30 lines of bash; rationale lives in the spec + `lib-run.sh` comments).

**Files:**
- Modify: `docs/adr/0016-local-scheduling-and-notification.md`

- [ ] **Step 1: Append the pointer to the Consequences section**

In `docs/adr/0016-local-scheduling-and-notification.md`, find the last bullet of the `## Consequences` list (currently line 94):

```
- No pipeline exit code or artifact contract changes — item 002 only consumes them.
```

and add a new bullet immediately after it:

```
- **Wrapper robustness (2026-06-30):** the surviving launchd wrappers regained a
  portable wall-clock watchdog (process-group kill → `rc=124`) and per-wrapper
  single-instance locks via the shared `ops/launchd/lib-run.sh`. Design + rationale:
  `docs/2026-06-30-launchd-watchdog/items/001-spec.md` (no standalone ADR — reversible).
```

- [ ] **Step 2: Verify**

Run: `grep -n "lib-run.sh\|launchd-watchdog" docs/adr/0016-local-scheduling-and-notification.md`
Expected: the new bullet's two references appear.

- [ ] **Step 3: Commit**

```bash
git add docs/adr/0016-local-scheduling-and-notification.md
git commit -m "docs(adr): point ADR 0016 at the wrapper watchdog + lock spec"
```

---

## Task 11: CHANGELOG `[Unreleased]` entry + TODOS note

Spec §7 files-touched table: `CHANGELOG.md` `[Unreleased]` entry; record the follow-up. Per the project's versioning convention (memory: do NOT bump VERSION per feature PR), accumulate under `[Unreleased]` at the static VERSION.

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `TODOS.md`

- [ ] **Step 1: Add the CHANGELOG entry**

In `CHANGELOG.md`, find the `## [Unreleased]` heading (line 8) and insert this new section immediately **after** it (above the existing "Fixed — monitor completion sentinel…" section so the newest entry is first):

```markdown
### Added — launchd wrapper watchdog + single-instance lock restored via shared `lib-run.sh` (2026-06-30)

- **New `ops/launchd/lib-run.sh`** defines two pure-bash helpers reused by both
  surviving wrappers: `acquire_lock <lock_dir>` (atomic `mkdir` lock with
  stale-holder reclaim + `EXIT`-trap release) and `run_with_watchdog <timeout> <cmd…>`
  (background under bash job control, poll on the `IRC_WATCHDOG_POLL` cadence using
  the `$SECONDS` wall-clock builtin, and on overrun kill the whole **process group**
  TERM→grace→KILL, returning `rc=124`). Restores the watchdog + lock that were lost
  when `run-daily.sh` was deleted in the single-daily-12:15 schedule rework (#178).
- **`run-monitor.sh`** now acquires `outputs/_logs/.monitor.lock` (after the
  once-per-day skip) and runs `irc monitor` under the watchdog
  (`IRC_MONITOR_TIMEOUT`, default 1800s). A timeout yields `rc=124`, which
  `notify-status` pages as "timeout". Lock contention is a silent `exit 0`.
- **`run-fundamentals.sh`** now acquires `outputs/_logs/.snapshot.lock` and runs
  `irc monitor snapshot` under the watchdog (`IRC_SNAPSHOT_TIMEOUT`, default 3600s).
  **Protective-only:** a snapshot timeout is logged loudly but does NOT page (no
  completion sentinel to test; the next daily brief degrades affected factors to N/A).
- **Process-group kill correction:** `uv run` spawns a Python child, so the old
  single-PID kill could orphan the worker (continued paid spend + a late
  `monitor.json` write). The watchdog now signals the negative PID under `set -m`.
- **Docs:** fixed `ops/launchd/README.md`'s false `outputs/_logs/.run.lock` claim
  (the lock never existed) and documented both timeouts + the notify asymmetry; one-line
  pointer added to ADR 0016. Design: `docs/2026-06-30-launchd-watchdog/items/001-spec.md`.
- **Tests:** new `tests/ops/test_run_lib.py` (library unit tests incl. process-group
  grandchild-kill + `IRC_WATCHDOG_POLL` fast path); extended
  `tests/ops/test_launchd_monitor.py` (timeout-kill→notify-124, lock-held→uv-not-called,
  watchdog-presence on both wrappers); `tests/commands/test_notify_cmd.py` asserts
  `lib-run.sh` defines both functions.
```

- [ ] **Step 2: Add the TODOS note**

In `TODOS.md`, find the line:

```
- [ ] **`_ak_call` has no timeout enforcement** — AkShare's internal HTTP calls run unbounded.
```

and append to the end of that bullet (after its existing `(item-001 ship adversarial review 2026-05-26)` parenthetical), as a continuation:

```
 — **Partial mitigation (2026-06-30):** the launchd wrappers now bound the *whole run* with a wall-clock watchdog (`ops/launchd/lib-run.sh::run_with_watchdog`, `IRC_MONITOR_TIMEOUT`/`IRC_SNAPSHOT_TIMEOUT`) that kills the process group on a no-timeout network hang. This caps unattended exposure but does NOT replace a per-`_ak_call` deadline (a manual `irc monitor` is still unbounded). See `docs/2026-06-30-launchd-watchdog/items/001-spec.md` threat model.
```

- [ ] **Step 3: Verify the CHANGELOG entry sits under `[Unreleased]`**

Run: `grep -n "launchd wrapper watchdog\|run_with_watchdog\|IRC_SNAPSHOT_TIMEOUT" CHANGELOG.md`
Expected: matches inside the `[Unreleased]` block (line numbers above the older "monitor completion sentinel" section, all > line 8).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md TODOS.md
git commit -m "docs: changelog [Unreleased] for launchd watchdog+lock; note wrapper-level _ak_call mitigation"
```

---

## Task 12: Final full verification

A single sweep over every artifact the spec touches.

**Files:** none (verification only)

- [ ] **Step 1: bash -n every launchd script (incl. the new library)**

Run:
```bash
for s in ops/launchd/*.sh; do echo "== $s =="; bash -n "$s" && echo OK; done
```
Expected: every script prints `OK` (no syntax errors), incl. `lib-run.sh`, `run-monitor.sh`, `run-fundamentals.sh`, `install.sh`, `uninstall.sh`.

- [ ] **Step 2: plutil-lint every plist (must remain untouched/valid)**

Run: `plutil -lint ops/launchd/*.plist`
Expected: each plist prints `OK` (this feature does not change plists; the lint confirms no accidental edit).

- [ ] **Step 3: Run the three affected test files**

Run: `uv run pytest tests/ops/test_run_lib.py tests/ops/test_launchd_monitor.py tests/commands/test_notify_cmd.py -q`
Expected: all pass. Approximate counts: `test_run_lib.py` = **6 passed**; `test_launchd_monitor.py` = pre-existing tests + **8 new** (Tasks 5–7: 2 timeout/lock monitor + 2 timeout/lock snapshot + 4 presence) all passed; `test_notify_cmd.py` = pre-existing + **1 new** passed.

> Do NOT run `uv run pytest tests/commands/` as a whole directory — per project memory it can hang on suite ordering. Run `tests/commands/test_notify_cmd.py` by file path as shown.

- [ ] **Step 4: ruff lint (Python tests only — bash is not linted by ruff)**

Run: `uv run ruff check tests/ops/test_run_lib.py tests/ops/test_launchd_monitor.py tests/commands/test_notify_cmd.py`
Expected: `All checks passed!` (line-length 100, py312).

- [ ] **Step 5: Confirm the library has no install-time placeholders**

Run: `grep -n "__UV_BIN__\|__REPO_ROOT__" ops/launchd/lib-run.sh`
Expected: no output (the library is pure logic, checked in verbatim — spec §3).

- [ ] **Step 6: Confirm wrappers source the lib AFTER `cd "$REPO_ROOT"`**

Run:
```bash
for w in run-monitor.sh run-fundamentals.sh; do
  echo "== $w =="
  grep -n 'cd "\$REPO_ROOT"\|source ops/launchd/lib-run.sh' "ops/launchd/$w"
done
```
Expected: for each wrapper, the `source ops/launchd/lib-run.sh` line number is **greater** than the `cd "$REPO_ROOT"` line number.

- [ ] **Step 7: Final commit (only if any verification surfaced a fix; otherwise skip)**

> **Plan amendment (deviation f — ruff cleanup):** The ruff check (Step 4) flagged unused `textwrap` and `pytest` imports in `tests/ops/test_run_lib.py` (added in Task 1's initial commit but never used once the test structure was finalized). The verification sweep commit removed them. This is expected ruff hygiene; the plan already mandated `All checks passed!` so this is consistent.

```bash
git add -A
git commit -m "chore(launchd): verification sweep for watchdog+lock"
```

---

## Self-Review (author's checklist — completed)

**Spec coverage** (every §7 files-touched row maps to a task):

| §7 file | Task |
|---|---|
| `ops/launchd/lib-run.sh` (new) | Tasks 1 (run_with_watchdog) + 4 (acquire_lock) |
| `ops/launchd/run-monitor.sh` | Task 5 |
| `ops/launchd/run-fundamentals.sh` | Task 6 |
| `ops/launchd/README.md` | Task 9 |
| `docs/adr/0016-*.md` | Task 10 |
| `tests/ops/test_run_lib.py` (new, incl. process-group kill + `IRC_WATCHDOG_POLL`) | Tasks 1–4 |
| `tests/ops/test_launchd_monitor.py` (timeout-kill, lock-skip, watchdog-presence) | Tasks 5, 6, 7 |
| `tests/commands/test_notify_cmd.py` (both-functions assertion) | Task 8 |
| `CHANGELOG.md` / `TODOS.md` | Task 11 |

Locked-decision coverage (spec §1–§4, §8): process-group kill via `set -m` + negative PID (Task 1, tested Task 3); `$SECONDS` wall-clock (Task 1); `IRC_WATCHDOG_POLL` knob default 10/tests 0.2 (Task 1, tested Task 2); mkdir-atomic lock + stale-reclaim + `EXIT` trap + `$$` pid (Task 4); `rc=0; … || rc=$?` calling convention (Tasks 5–6); silent `exit 0` on contention, no notify (Tasks 5–6, tested 5/6); per-wrapper `.monitor.lock` / `.snapshot.lock` (Tasks 5/6/9); lib sourced after `cd` via relative path (Tasks 5/6, verified Task 12); lib has no placeholders (Task 1, verified Task 12); no SIGTERM handler / no GNU timeout (never added); monitor timeout 1800 + notify-124 (Task 5); snapshot timeout 3600 + protective-only no-notify (Task 6).

**TDD red-first:** every new bash function (Tasks 1, 4) and every wrapper wiring (Tasks 5, 6) writes the failing behavioral test first, runs it to confirm the *right* failure, then implements. Tasks 2/3/7 are tests that go green against already-committed behavior — each step says so and instructs "fix the impl, don't weaken the test" if red.

**Placeholder scan:** no TBD/TODO-in-code/"add error handling"/"similar to Task N" — all bash and Python is shown verbatim.

**Type/name consistency:** function names `acquire_lock` / `run_with_watchdog`, lock dirs `outputs/_logs/.monitor.lock` / `outputs/_logs/.snapshot.lock`, env vars `IRC_MONITOR_TIMEOUT` (1800) / `IRC_SNAPSHOT_TIMEOUT` (3600) / `IRC_WATCHDOG_POLL` (10) are used identically across the library, wrappers, tests, docs, and CHANGELOG.

**Judgment call (surfaced):** the spec §7 row says "TODOS.md close the watchdog follow-up item", but no standalone open watchdog/lock TODO exists in `TODOS.md` — the resolved #179 sentinel item (line 22) is already `[x]`, and there is no separate "restore the watchdog" entry. The closest open item is the `_ak_call` unbounded-network-hang TODO (line 17). Task 11 therefore annotates *that* item as partially mitigated by this wrapper-level watchdog (the honest relationship — the wrapper caps unattended exposure but is not a per-call deadline) rather than fabricating-then-closing a non-existent item. The implementer should not search for and check off a watchdog TODO that isn't there.
