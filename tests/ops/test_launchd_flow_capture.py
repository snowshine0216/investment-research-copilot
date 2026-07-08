"""AC6/§3.4: run-flow-capture.sh gains a best-effort notify tail with the
flow-capture run-kind, --no-notify-on-clean, and the authoritative $rc."""
from __future__ import annotations

import subprocess
from pathlib import Path

_WRAPPER = Path(__file__).parents[2] / "ops" / "launchd" / "run-flow-capture.sh"


def test_wrapper_calls_notify_flow_capture_silent_on_clean():
    text = _WRAPPER.read_text(encoding="utf-8")
    assert '"$UV_BIN" run irc notify-status --run-kind flow-capture' in text
    assert "--no-notify-on-clean" in text
    assert '--last-exit-code "$rc"' in text


def test_wrapper_notify_tail_after_rotation_and_before_exit():
    lines = _WRAPPER.read_text(encoding="utf-8").splitlines()
    notify_idx = next(i for i, ln in enumerate(lines) if "notify-status --run-kind flow-capture" in ln)
    rotation_idx = next(i for i, ln in enumerate(lines) if "irc rotation" in ln and "run_with_watchdog" in ln)
    exit_idx = next(i for i, ln in enumerate(lines) if ln.strip() == 'exit "$rc"')
    assert rotation_idx < notify_idx < exit_idx


def test_wrapper_notify_failure_does_not_abort():
    # Mirror run-monitor.sh: the tail must be `|| echo ...`, never bare, so a
    # notifier failure cannot abort the wrapper under set -e.
    text = _WRAPPER.read_text(encoding="utf-8")
    assert "|| echo" in text
    assert "notify-status failed" in text


def test_wrapper_passes_bash_syntax_check():
    result = subprocess.run(["bash", "-n", str(_WRAPPER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
