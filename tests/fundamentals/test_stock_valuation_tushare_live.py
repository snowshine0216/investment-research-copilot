"""Live verification of Tushare daily_basic columns (Phase D PR1, gate #4).

TRIPLE-gated: requires the `live_tushare` marker, `IRC_RUN_LIVE_TUSHARE=1`, AND
a real TUSHARE_TOKEN in the environment. Default `pytest` skips it.

AUTHORED in PR1 but NOT executed by the autodev loop (gate #4 is human).

Run (human, gate #4)::

    IRC_RUN_LIVE_TUSHARE=1 uv run pytest -m live_tushare \\
        tests/fundamentals/test_stock_valuation_tushare_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    fetch_stock_valuation_history_tushare,
)

_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
_RUN = os.environ.get("IRC_RUN_LIVE_TUSHARE") == "1"
pytestmark = [
    pytest.mark.live_tushare,
    pytest.mark.skipif(
        not (_RUN and _TOKEN),
        reason="set IRC_RUN_LIVE_TUSHARE=1 and TUSHARE_TOKEN to run live Tushare tests",
    ),
]


def test_fetch_daily_basic_kweichow_moutai_live() -> None:
    """600519 returns a real history; pe_ttm/pb numeric. Pins daily_basic cols."""
    out = fetch_stock_valuation_history_tushare("600519", token=_TOKEN)
    assert isinstance(out, StockValuationHistory)
    assert out.rows, "daily_basic returned no parseable rows"
    latest = out.rows[-1]
    assert latest.pe_ttm is not None and latest.pe_ttm > 0
    assert latest.pb is not None and latest.pb > 0
    print(f"\n  ✓ 600519 tushare live: {len(out.rows)} rows, "
          f"pe={latest.pe_ttm} pb={latest.pb} dv={latest.dividend_yield}")
