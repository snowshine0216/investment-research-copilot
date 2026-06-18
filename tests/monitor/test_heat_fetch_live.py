"""Live AkShare probe for the heat restriction leg (spec §8 — Live).

DOUBLE-GATED: BOTH ``IRC_RUN_LIVE_AKSHARE=1`` AND ``-m live_akshare`` are required.
Without the env var the module-level ``pytestmark`` skips every test here — this
makes ONE real ``ak.fund_purchase_em()`` call and is out of the offline suite.

Run::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest tests/monitor/test_heat_fetch_live.py -v -m live_akshare
"""
from __future__ import annotations

import os

import pytest

from irc.monitor.heat_fetch import (
    fetch_purchase_table,
    heat_inputs_for,
    parse_purchase_status,
)

pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        os.environ.get("IRC_RUN_LIVE_AKSHARE") != "1",
        reason="double-gated: set IRC_RUN_LIVE_AKSHARE=1 to hit AkShare",
    ),
]

_MONITOR_IDS = ["008986", "270023", "519069", "260112", "006533", "009225",
                "000083", "519770", "018132", "161903"]


def test_purchase_table_reachable_and_all_ids_parse():
    """ONE real call → table reachable; every monitor id parses to a real bool."""
    table = fetch_purchase_table()  # default: real ak.fund_purchase_em via lazy import
    assert table is not None, "fund_purchase_em returned None — network error or empty result."
    for fund_id in _MONITOR_IDS:
        restricted, aum = heat_inputs_for(fund_id, purchase_table=table)
        assert restricted in (True, False), (
            f"{fund_id} did not parse to a bool (got {restricted!r}) — schema drift? "
            "Check 申购状态 / 日累计限定金额 column names in heat_fetch."
        )
        assert aum is None  # AUM-Δ leg deferred this slice.


def test_missing_id_parses_to_none_gracefully():
    """A fund absent from the table degrades to None (→ heat_no_data), not an error."""
    table = fetch_purchase_table()
    assert table is not None
    assert parse_purchase_status(table, "999999") is None
