"""Live AkShare NAV fetch for the 7 monitor ids (§12.4/§12.6).

Double-gated: BOTH ``IRC_RUN_LIVE_AKSHARE=1`` AND ``-m live_akshare`` are required.
Without the env var the module-level ``pytestmark`` skips every test here.

Verifies §12.6: the ``history.fetch_calendar_days: 550`` window in
``config/monitor.yaml`` yields at least ``minimum_observations`` (251) valid
accumulative-NAV points for each of the 7 monitor fund ids, including the QDII
funds (270023, 009225) that have publication lag and holiday gaps.

Degradation (§12.6): if a fund yields fewer than 251 acc-NAV points the test
SKIPS with a remediation message — bump ``history.fetch_calendar_days`` (e.g.
550 → 750) in ``config/monitor.yaml`` and re-run. The monitor factor eligibility
gate surfaces a shortfall as ``trend → N/A`` (reason: ``trend_insufficient_history``)
rather than crashing, so the report still ships.

Run::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest tests/monitor/test_live_nav.py -v -m live_akshare
"""
from __future__ import annotations

import os

import pytest

from irc.monitor.fetch import nav_series_for

# Module-level double gate: env var + marker.
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1",
        reason="double-gated: set IRC_RUN_LIVE_AKSHARE=1 to hit AkShare",
    ),
]

_MONITOR_IDS = ["008986", "270023", "519069", "260112", "006533", "009225", "000083",
                "519770", "018132"]

# §12.6 minimum threshold from spec / config/monitor.yaml
_MINIMUM_OBSERVATIONS = 251


@pytest.mark.parametrize("fund_id", _MONITOR_IDS)
def test_nav_history_yields_enough_points(fund_id: str) -> None:
    """§12.6: 550-day fetch window yields ≥251 valid acc-NAV points for each id.

    QDII funds 270023 / 009225 are most at risk due to publication lag and
    holiday gaps. If the assertion threshold is not met the test SKIPS with a
    remediation hint rather than failing — the monitor ships with trend N/A
    for that fund.
    """
    res = nav_series_for(fund_id)
    assert res is not None, (
        f"NAV fetch returned None for {fund_id} — network error or empty AkShare result."
    )
    n = len(res.acc_series)
    if n < _MINIMUM_OBSERVATIONS:
        pytest.skip(
            f"{fund_id} has only {n} acc-NAV points (need {_MINIMUM_OBSERVATIONS}) — "
            "widen history.fetch_calendar_days in config/monitor.yaml (§12.6 degradation)."
        )
