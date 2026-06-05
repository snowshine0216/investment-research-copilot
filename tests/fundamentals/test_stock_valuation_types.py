from __future__ import annotations

import dataclasses

import pytest

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)


def test_point_is_frozen_with_nullable_metrics() -> None:
    pt = StockValuationPoint(date_iso="2026-05-30", pe_ttm=18.2, pb=2.1, dividend_yield=None)
    assert pt.date_iso == "2026-05-30"
    assert pt.dividend_yield is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        pt.pe_ttm = 1.0  # type: ignore[misc]


def test_history_carries_stock_code_and_rows() -> None:
    hist = StockValuationHistory(
        stock_code="600519",
        rows=(StockValuationPoint("2026-05-30", 18.2, 2.1, None),),
    )
    assert hist.stock_code == "600519"
    assert len(hist.rows) == 1
