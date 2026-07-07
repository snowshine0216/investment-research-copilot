"""Static assertions for the 15:45 flow-capture wrapper notify tail
(data-health-notify, mirror of run-monitor.sh's notify assertions)."""
from __future__ import annotations

import subprocess
from pathlib import Path

_OPS = Path(__file__).parents[2] / "ops" / "launchd"


def _text() -> str:
    return (_OPS / "run-flow-capture.sh").read_text(encoding="utf-8")


def test_flow_capture_calls_notify_status_with_flow_capture_kind():
    text = _text()
    assert "notify-status" in text and "--run-kind flow-capture" in text


def test_flow_capture_notify_hardcodes_no_notify_on_clean():
    assert "--no-notify-on-clean" in _text()


def test_flow_capture_notify_passes_flow_capture_rc():
    # Authoritative flow-capture $rc, NOT the advisory $radar_rc.
    assert '--last-exit-code "$rc"' in _text()


def test_flow_capture_notify_after_trading_day_gates():
    text = _text()
    assert text.index("notify-status") > text.index("weekend — skipping"), (
        "notify tail must sit after the weekend/holiday gates (no non-trading-day noise)"
    )


def test_flow_capture_notify_after_rotation_step():
    text = _text()
    assert text.index("notify-status") > text.index("irc rotation"), (
        "notify tail must run after the rotation step"
    )


def test_flow_capture_still_exits_with_flow_capture_rc():
    assert 'exit "$rc"' in _text()


def test_flow_capture_bash_syntax():
    result = subprocess.run(
        ["bash", "-n", str(_OPS / "run-flow-capture.sh")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
