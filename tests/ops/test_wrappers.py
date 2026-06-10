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

    # For run-daily.sh: force a non-weekend CN date so the trading-day gate passes.
    # We do this by pointing to a non-existent holiday file and patching the
    # date via TZ=UTC+8 (Wednesday 2026-06-10, DOW=3 → not weekend).
    # For run-weekly-full.sh: no gate, runs unconditionally.
    templated = _template_wrapper(src, tmp_path, stub)

    # Shorten the watchdog timeout so the test completes quickly, but ensure the
    # pipeline "exits" before the watchdog fires (the stub exits immediately).
    env = {"IRC_RUN_TIMEOUT": "60"}

    result = _run_wrapper(templated, env=env)

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
    env = {"IRC_RUN_TIMEOUT": "60"}

    _run_wrapper(templated, env=env)

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
