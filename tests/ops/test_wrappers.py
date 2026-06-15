"""Regression tests for ops/launchd wrapper scripts.

P0: verify that a non-zero exit from the backgrounded pipeline still reaches the
    notify-status invocation — i.e. `wait "$_PID" || rc=$?` captures the exit code
    even when `set -euo pipefail` is active.

The strategy (per the adversarial-review spec):
- Substitute __UV_BIN__ in the real wrapper source with a stub script that exits
  with a chosen code and records its argv.
- Also substitute __REPO_ROOT__ with a tmp dir that satisfies `cd "$REPO_ROOT"`.
- Run the templated wrapper under `bash` with the stub on PATH.
- Assert that the stub was called a *second* time with `notify-status` and the
  expected `--last-exit-code`.

Covers both run-daily.sh and run-weekly-full.sh.
"""
from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[2]
_OPS = _REPO_ROOT / "ops" / "launchd"

# Fixed CN-clock gate dates (date string, ISO day-of-week) so the trading-day
# gate in run-daily.sh is independent of the real calendar.
_GATE_OPEN_DAY = ("2026-06-10", "3")  # Wednesday — gate passes
_GATE_CLOSED_DAY = ("2026-06-13", "6")  # Saturday — gate skips


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stub(tmp_path: Path, exit_code: int) -> tuple[Path, Path]:
    """Return (stub_path, argv_log_path).

    The stub is a bash script that:
    - Logs all invocation argv to argv_log_path (one invocation per line, args
      space-joined, separated by '---').
    - When called as `uv run irc run`, exits with exit_code.
    - When called as `uv run irc notify-status ...`, exits 0 and records args.
    """
    argv_log = tmp_path / "stub_argv.log"
    stub = tmp_path / "uv"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            # Stub: log argv, simulate irc run exit code or notify-status success.
            echo "$@" >> {argv_log}
            # Detect the sub-command: "run irc notify-status" → exit 0
            # "run irc run" → exit with configured code
            for arg in "$@"; do
              if [ "$arg" = "notify-status" ]; then
                exit 0
              fi
            done
            exit {exit_code}
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return stub, argv_log


def _template_wrapper(src: Path, tmp_path: Path, stub: Path) -> Path:
    """Replace __UV_BIN__ and __REPO_ROOT__ in src; write to tmp_path/name."""
    text = src.read_text(encoding="utf-8")
    text = text.replace("__UV_BIN__", str(stub))
    text = text.replace("__REPO_ROOT__", str(tmp_path))
    out = tmp_path / src.name
    out.write_text(text, encoding="utf-8")
    out.chmod(out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return out


def _make_date_stub(tmp_path: Path, day: str, dow: str) -> Path:
    """Return a bin dir whose `date` reports a fixed CN-clock day to the gate.

    Answers the two trading-day-gate formats (+%Y-%m-%d, +%u) with the given
    values; any other format falls through to the system date (watchdog line).
    """
    bin_dir = tmp_path / "datebin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "date"
    stub.write_text(
        textwrap.dedent(f"""\
            #!/bin/bash
            case "$1" in
              "+%Y-%m-%d") echo "{day}" ;;
              "+%u") echo "{dow}" ;;
              *) exec /bin/date "$@" ;;
            esac
        """),
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _wrapper_env(date_bin: Path) -> dict:
    """Env for templated-wrapper runs: short watchdog + stubbed date on PATH."""
    return {
        "IRC_RUN_TIMEOUT": "60",
        "PATH": f"{date_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }


def _run_wrapper(wrapper: Path, env: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a wrapper script and return the CompletedProcess."""
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged_env,
    )


def _read_argv_log(argv_log: Path) -> list[str]:
    """Return list of recorded argv strings (one per stub invocation)."""
    if not argv_log.exists():
        return []
    return [line for line in argv_log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_run_log(tmp_path: Path, prefix: str) -> str:
    """Return the concatenated contents of the wrapper's own per-run log file(s).

    The hardened wrappers redirect their own stdout/stderr to a fresh
    `outputs/_logs/<prefix>.<timestamp>.log` (launchd writes to /dev/null — the
    com.apple.provenance reopen-denial fix). Gate/guard messages land there, not
    on the wrapper process's stdout.
    """
    log_dir = tmp_path / "outputs" / "_logs"
    if not log_dir.exists():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(log_dir.glob(f"{prefix}.*.log"))
    )


# ---------------------------------------------------------------------------
# P0: wait exit-capture regression
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wrapper_name", ["run-daily.sh", "run-weekly-full.sh"])
def test_nonzero_pipeline_exit_reaches_notify_status(tmp_path: Path, wrapper_name: str):
    """P0 regression: pipeline exit code 3 must be forwarded to notify-status.

    With `wait "$_PID"` (without `|| rc=$?`), set -e would abort the script the
    moment wait returns non-zero, making the notify-status call dead code.
    This test exercises the REAL wrapper file (templated) to prove the fix works.
    """
    stub, argv_log = _make_stub(tmp_path, exit_code=3)
    src = _OPS / wrapper_name

    # run-daily.sh gates on the CN-clock date (skips Sat/Sun + holidays). Pin
    # the clock via a stub `date` on PATH so the gate passes deterministically;
    # the holiday YAML is absent under the tmp REPO_ROOT, so that leg is off.
    # run-weekly-full.sh has no gate; the stub is harmless there.
    templated = _template_wrapper(src, tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)

    # IRC_RUN_TIMEOUT shortens the watchdog so the test completes quickly, but
    # the pipeline stub exits long before it fires.
    result = _run_wrapper(templated, env=_wrapper_env(date_bin))

    invocations = _read_argv_log(argv_log)

    # The stub must have been called at least twice: once for "irc run" (exits 3)
    # and once for "irc notify-status".
    notify_calls = [line for line in invocations if "notify-status" in line]
    assert notify_calls, (
        f"{wrapper_name}: notify-status was never called after pipeline exited 3.\n"
        f"Stub invocations: {invocations}\n"
        f"Wrapper stdout: {result.stdout}\n"
        f"Wrapper stderr: {result.stderr}"
    )

    # Verify --last-exit-code 3 was passed to notify-status.
    assert any("--last-exit-code" in c and "3" in c for c in notify_calls), (
        f"{wrapper_name}: notify-status not called with --last-exit-code 3.\n"
        f"Notify calls: {notify_calls}"
    )


@pytest.mark.parametrize("wrapper_name", ["run-daily.sh", "run-weekly-full.sh"])
def test_zero_pipeline_exit_reaches_notify_status(tmp_path: Path, wrapper_name: str):
    """Sanity: a successful (exit 0) pipeline also reaches notify-status with --last-exit-code 0."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / wrapper_name, tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)

    _run_wrapper(templated, env=_wrapper_env(date_bin))

    invocations = _read_argv_log(argv_log)
    notify_calls = [line for line in invocations if "notify-status" in line]
    assert notify_calls, (
        f"{wrapper_name}: notify-status not called for exit-0 run.\n"
        f"Stub invocations: {invocations}"
    )
    assert any("--last-exit-code" in c and c.endswith("0") for c in notify_calls), (
        f"{wrapper_name}: expected --last-exit-code 0 in notify call.\n"
        f"Notify calls: {notify_calls}"
    )


def test_daily_gate_skips_weekend_before_pipeline(tmp_path: Path):
    """The trading-day gate must exit 0 on a CN weekend without invoking uv at all."""
    stub, argv_log = _make_stub(tmp_path, exit_code=3)
    templated = _template_wrapper(_OPS / "run-daily.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_CLOSED_DAY)

    result = _run_wrapper(templated, env=_wrapper_env(date_bin))

    assert result.returncode == 0
    # The wrapper redirects its own output to a per-run log (launchd → /dev/null).
    assert "weekend" in _read_run_log(tmp_path, "run-daily")
    assert _read_argv_log(argv_log) == [], (
        f"gate must short-circuit before the pipeline; stub was invoked: "
        f"{_read_argv_log(argv_log)}"
    )


# ---------------------------------------------------------------------------
# P0: com.apple.provenance fix — launchd logs must be /dev/null; the wrapper
#     writes its own fresh per-run log so launchd never reopens a tagged file.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "plist_name,stale_marker",
    [
        ("com.irc.daily.plist", "launchd-daily"),
        ("com.irc.weekly-full.plist", "launchd-weekly"),
    ],
)
def test_plist_logs_to_devnull(plist_name: str, stale_marker: str):
    """launchd StandardOut/ErrPath must be /dev/null (provenance reopen-denial fix)."""
    text = (_OPS / plist_name).read_text(encoding="utf-8")
    assert text.count("<string>/dev/null</string>") >= 2, (
        f"{plist_name}: StandardOutPath and StandardErrorPath must both be /dev/null"
    )
    assert stale_marker not in text, (
        f"{plist_name}: must not point launchd at a {stale_marker}.*.log file "
        f"(those acquire com.apple.provenance and become unopenable on reopen)"
    )


def test_daily_plist_has_redundant_fire_times():
    """Daily plist must fire at 17:30, 20:00 and 22:30 so a missed/asleep slot is
    caught later (idempotency guard makes the redundant fires safe)."""
    text = (_OPS / "com.irc.daily.plist").read_text(encoding="utf-8")
    # 17:30 + 20:00 + 22:30 across Mon–Fri = three distinct hours.
    assert "<integer>20</integer>" in text, "daily plist missing the 20:00 catch-up fire"
    assert "<integer>22</integer>" in text, "daily plist missing the 22:30 catch-up fire"
    # Still Mon–Fri only (no weekend weekday 6/7 entries).
    assert "<integer>6</integer>" not in text and "<integer>7</integer>" not in text


@pytest.mark.parametrize("wrapper_name,prefix", [("run-daily.sh", "run-daily"), ("run-weekly-full.sh", "run-weekly")])
def test_wrapper_writes_own_fresh_run_log(tmp_path: Path, wrapper_name: str, prefix: str):
    """Each run must create a fresh outputs/_logs/<prefix>.<ts>.log it owns."""
    stub, _ = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / wrapper_name, tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)

    _run_wrapper(templated, env=_wrapper_env(date_bin))

    logs = list((tmp_path / "outputs" / "_logs").glob(f"{prefix}.*.log"))
    assert logs, f"{wrapper_name}: expected a fresh {prefix}.<ts>.log under outputs/_logs"


# ---------------------------------------------------------------------------
# Idempotency guard (daily): skip when today's run already succeeded.
# ---------------------------------------------------------------------------

def _seed_today_outputs(tmp_path: Path, day: str, *, decision: bool, halted: bool) -> None:
    out = tmp_path / "outputs" / day
    out.mkdir(parents=True, exist_ok=True)
    if decision:
        (out / "decision_report.md").write_text("# decision\n", encoding="utf-8")
    if halted:
        (out / "PIPELINE_HALTED.md").write_text("# halted\n", encoding="utf-8")


def test_daily_idempotency_skips_when_today_completed(tmp_path: Path):
    """A completed run today (decision_report.md, no halt marker) must skip the
    pipeline so redundant fire times don't re-run it."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / "run-daily.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)
    _seed_today_outputs(tmp_path, _GATE_OPEN_DAY[0], decision=True, halted=False)

    result = _run_wrapper(templated, env=_wrapper_env(date_bin))

    assert result.returncode == 0
    assert _read_argv_log(argv_log) == [], "idempotency guard must skip the pipeline"
    assert "already completed" in _read_run_log(tmp_path, "run-daily")


def test_daily_idempotency_runs_when_prior_run_halted(tmp_path: Path):
    """A halted run today (PIPELINE_HALTED.md present) must RE-RUN (retry)."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / "run-daily.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)
    _seed_today_outputs(tmp_path, _GATE_OPEN_DAY[0], decision=True, halted=True)

    _run_wrapper(templated, env=_wrapper_env(date_bin))

    assert _read_argv_log(argv_log), "guard must retry when today's run halted"


# ---------------------------------------------------------------------------
# Single-instance lock: skip when a live run holds it; steal a stale lock.
# ---------------------------------------------------------------------------

def _seed_lock(tmp_path: Path, pid: int) -> None:
    lock = tmp_path / "outputs" / "_logs" / ".run.lock"
    lock.mkdir(parents=True, exist_ok=True)
    (lock / "pid").write_text(str(pid), encoding="utf-8")


def test_lock_skips_when_held_by_live_process(tmp_path: Path):
    """If another run holds the lock (live pid), skip rather than collide."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / "run-daily.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)
    _seed_lock(tmp_path, os.getpid())  # the test process is alive

    result = _run_wrapper(templated, env=_wrapper_env(date_bin))

    assert result.returncode == 0
    assert _read_argv_log(argv_log) == [], "must not run while another holds the lock"
    assert "in progress" in _read_run_log(tmp_path, "run-daily")


def test_lock_steals_stale_lock_and_runs(tmp_path: Path):
    """A stale lock (dead pid) must be reclaimed so a real run proceeds."""
    stub, argv_log = _make_stub(tmp_path, exit_code=0)
    templated = _template_wrapper(_OPS / "run-daily.sh", tmp_path, stub)
    date_bin = _make_date_stub(tmp_path, *_GATE_OPEN_DAY)
    _seed_lock(tmp_path, 999999)  # not a live pid

    _run_wrapper(templated, env=_wrapper_env(date_bin))

    assert _read_argv_log(argv_log), "must steal a stale lock and run the pipeline"


# ---------------------------------------------------------------------------
# P2: BSD-safe date quoting in watchdog log line
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wrapper_name", ["run-daily.sh", "run-weekly-full.sh"])
def test_watchdog_date_format_is_quoted(wrapper_name: str):
    """P2: `date '+%Y-%m-%d %H:%M'` must be single-quoted (BSD date safety)."""
    text = (_OPS / wrapper_name).read_text(encoding="utf-8")
    # The pattern `date +%Y` (unquoted, with a space in the format string) breaks BSD date.
    # After the fix the watchdog line must use `date '+%Y-%m-%d %H:%M'`.
    assert "date '+%Y-%m-%d %H:%M'" in text, (
        f"{wrapper_name}: watchdog date format must be single-quoted: date '+%Y-%m-%d %H:%M'"
    )
    # Make sure the old unquoted form is gone.
    assert "date +%Y-%m-%d %H:%M" not in text.replace("date '+%Y-%m-%d %H:%M'", ""), (
        f"{wrapper_name}: unquoted 'date +%Y-%m-%d %H:%M' still present"
    )


# ---------------------------------------------------------------------------
# P1: install.sh TZ warning present
# ---------------------------------------------------------------------------

def test_install_sh_contains_tz_warning():
    """P1: install.sh must warn when machine offset != +0800."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "+0800" in text, "install.sh must check for UTC+8 offset"
    assert "WARNING" in text, "install.sh must emit a WARNING when TZ != +0800"
