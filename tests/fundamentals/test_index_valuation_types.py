from __future__ import annotations

import dataclasses

from irc.fundamentals.index_valuation_types import (
    IndexValuationHistory,
    IndexValuationPoint,
)


def test_point_is_frozen_with_nullable_metrics() -> None:
    pt = IndexValuationPoint(date_iso="2026-05-30", pe_ttm=12.1, pb=1.31, dividend_yield=None)
    assert pt.date_iso == "2026-05-30"
    assert pt.pe_ttm == 12.1
    assert pt.pb == 1.31
    assert pt.dividend_yield is None
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        pt.pe_ttm = 99.0  # type: ignore[misc]


def test_history_holds_ordered_points() -> None:
    rows = (
        IndexValuationPoint("2026-05-28", 11.8, 1.28, None),
        IndexValuationPoint("2026-05-30", 12.1, 1.31, None),
    )
    hist = IndexValuationHistory(index_key="csi300", rows=rows)
    assert hist.index_key == "csi300"
    assert len(hist.rows) == 2
    assert hist.rows[-1].pe_ttm == 12.1
