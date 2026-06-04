"""Live verification of EastMoney stock_value_em columns (Phase D PR1, gate #4).

Double-gated: requires BOTH the `live_akshare` marker AND
`IRC_RUN_LIVE_AKSHARE=1`. Default `pytest` skips it. This is the single point
that pins the real `数据日期`/`PE(TTM)`/`市净率` column names; offline tests use
fixtures.

AUTHORED in PR1 but NOT executed by the autodev loop — column-string
confirmation against real EastMoney rows is human gate #4.

Run (human, gate #4)::

    IRC_RUN_LIVE_AKSHARE=1 uv run pytest -m live_akshare \\
        tests/fundamentals/test_stock_valuation_live.py -v -s
"""
from __future__ import annotations

import os

import pytest

from irc.fundamentals.akshare_stock_valuation import fetch_stock_valuation_history
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_RUN = os.environ.get("IRC_RUN_LIVE_AKSHARE") == "1"
pytestmark = [
    pytest.mark.live_akshare,
    pytest.mark.skipif(
        not _RUN,
        reason="set IRC_RUN_LIVE_AKSHARE=1 to run live AkShare tests",
    ),
]


def test_fetch_stock_value_em_kweichow_moutai_live() -> None:
    """600519 (贵州茅台) returns a real history with numeric PE and PB.

    If pe_ttm/pb come back all-None, the EastMoney column labels differ from
    `akshare_stock_valuation._PE_COL` / `_PB_COL` — inspect the live frame and
    correct the constants. This is the designed pin point (spec §3.5 gate #4).
    """
    out = fetch_stock_valuation_history("600519")
    assert isinstance(out, StockValuationHistory)
    assert out.rows, "stock_value_em returned no parseable rows"
    latest = out.rows[-1]
    assert latest.pe_ttm is not None, (
        "EastMoney PE(TTM) column not matched by _PE_COL — inspect the live "
        "frame and correct the constant."
    )
    assert latest.pb is not None, (
        "EastMoney 市净率 column not matched by _PB_COL — inspect the live frame."
    )
    assert latest.pe_ttm > 0 and latest.pb > 0
    assert latest.dividend_yield is None  # EastMoney exposes no per-stock div yield
    print(f"\n  ✓ 600519 live: {len(out.rows)} rows, "
          f"latest pe={latest.pe_ttm} pb={latest.pb}")
