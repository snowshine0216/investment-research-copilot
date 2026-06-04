from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from irc.fundamentals.akshare_stock_valuation import (
    _series_maps,
    fetch_stock_valuation_history,
)
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_FRAME = pd.DataFrame({
    "数据日期": ["2026-05-28", "2026-05-29", "2026-05-30"],
    "PE(TTM)": [18.0, 18.1, 18.2],
    "市净率": [2.0, 2.05, 2.1],
    "总市值": [1.0e12, 1.0e12, 1.0e12],
})


def test_series_maps_extracts_pe_and_pb_by_date() -> None:
    pe_map, pb_map = _series_maps(_FRAME)
    assert pe_map["2026-05-30"] == 18.2
    assert pb_map["2026-05-28"] == 2.0


def test_series_maps_empty_frame_returns_empty_maps() -> None:
    pe_map, pb_map = _series_maps(pd.DataFrame())
    assert pe_map == {} and pb_map == {}


def test_series_maps_coerces_non_numeric_to_none() -> None:
    frame = pd.DataFrame({"数据日期": ["2026-05-30"], "PE(TTM)": ["-"], "市净率": ["-"]})
    pe_map, pb_map = _series_maps(frame)
    assert pe_map["2026-05-30"] is None and pb_map["2026-05-30"] is None


def test_fetch_returns_history_with_dividend_yield_none() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call", return_value=_FRAME
    ):
        out = fetch_stock_valuation_history("600519")
    assert isinstance(out, StockValuationHistory)
    assert out.stock_code == "600519"
    assert len(out.rows) == 3
    assert out.rows[-1].pe_ttm == 18.2
    assert out.rows[-1].pb == 2.1
    assert all(r.dividend_yield is None for r in out.rows)


def test_fetch_degrades_to_none_on_empty_frame() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        return_value=pd.DataFrame(),
    ):
        assert fetch_stock_valuation_history("600519") is None


def test_fetch_degrades_to_none_on_raise() -> None:
    with patch(
        "irc.fundamentals.akshare_stock_valuation._ak_call",
        side_effect=RuntimeError("boom"),
    ):
        assert fetch_stock_valuation_history("600519") is None
