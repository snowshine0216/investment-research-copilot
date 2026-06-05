from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.stock_valuation_types import StockValuationHistory
from irc.fundamentals.tushare_stock_valuation import (
    _map_daily_basic,
    fetch_stock_valuation_history_tushare,
)

_FRAME = pd.DataFrame({
    "trade_date": ["20260528", "20260530"],
    "pe_ttm": [18.0, 18.2],
    "pb": [2.0, 2.1],
    "dv_ratio": [1.5, 1.6],  # percent units on Tushare
})


def test_map_daily_basic_extracts_pe_pb_and_dividend_ratio() -> None:
    hist = _map_daily_basic("600519", _FRAME)
    assert isinstance(hist, StockValuationHistory)
    assert hist.rows[0].date_iso == "2026-05-28"
    assert hist.rows[-1].pe_ttm == 18.2
    assert hist.rows[-1].pb == 2.1
    # dv_ratio 1.6% → 0.016 ratio
    assert abs(hist.rows[-1].dividend_yield - 0.016) < 1e-9


def test_map_daily_basic_missing_dv_ratio_leaves_dividend_none() -> None:
    frame = pd.DataFrame({"trade_date": ["20260530"], "pe_ttm": [18.2], "pb": [2.1]})
    hist = _map_daily_basic("600519", frame)
    assert hist is not None and hist.rows[0].dividend_yield is None


def test_map_daily_basic_empty_frame_returns_none() -> None:
    assert _map_daily_basic("600519", pd.DataFrame()) is None


def test_fetch_returns_none_without_token() -> None:
    assert fetch_stock_valuation_history_tushare("600519", token="") is None


def test_fetch_degrades_to_none_on_raise() -> None:
    with patch(
        "irc.fundamentals.tushare_stock_valuation._tushare_call",
        side_effect=RuntimeError("boom"),
    ):
        assert fetch_stock_valuation_history_tushare("600519", token="tok") is None


def test_fetch_maps_when_token_present() -> None:
    with patch(
        "irc.fundamentals.tushare_stock_valuation._tushare_call",
        return_value=_FRAME,
    ):
        out = fetch_stock_valuation_history_tushare("600519", token="tok")
    assert isinstance(out, StockValuationHistory)
    assert out.rows[-1].pe_ttm == 18.2
