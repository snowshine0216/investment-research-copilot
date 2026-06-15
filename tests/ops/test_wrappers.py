"""Regression tests for ops/launchd wrapper scripts.

After the Phase J schedule rework, the launchd ops now ship:
  - run-monitor.sh  (Mon-Fri 09:00 + 13:00 retry, trading-day gate, notify)
  - run-fundamentals.sh  (quarterly snapshot refresh)

The old run-daily.sh / run-weekly-full.sh wrappers and their plists were
removed as part of the monitor migration (Task 37). Tests that validated those
old wrappers now live in tests/ops/test_launchd_monitor.py.

This file retains:
  - install.sh TZ warning (P1 guard, still valid)
  - Backward-compat note: test_launchd_monitor.py covers the equivalent
    gate / idempotency / notify tests for run-monitor.sh.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]
_OPS = _REPO_ROOT / "ops" / "launchd"


# ---------------------------------------------------------------------------
# P1: install.sh TZ warning present
# ---------------------------------------------------------------------------


def test_install_sh_contains_tz_warning():
    """P1: install.sh must warn when machine offset != +0800."""
    text = (_OPS / "install.sh").read_text(encoding="utf-8")
    assert "+0800" in text, "install.sh must check for UTC+8 offset"
    assert "WARNING" in text, "install.sh must emit a WARNING when TZ != +0800"
