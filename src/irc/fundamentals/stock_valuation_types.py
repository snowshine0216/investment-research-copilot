"""Per-stock valuation snapshot types (Phase D PR1).

Frozen, immutable. All metric fields are `float | None` — every fetch path
degrades to None on failure / missing column, never raises. Mirrors
`index_valuation_types.py` for the per-A-share look-through path.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockValuationPoint:
    """One dated per-stock valuation observation (full history)."""
    date_iso: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None


@dataclass(frozen=True)
class StockValuationHistory:
    """Full PE/PB/dividend series for one A-share. Degrades to None at the
    fetch edge (unknown / adapter failure / empty frame), never raises."""
    stock_code: str
    rows: tuple[StockValuationPoint, ...]
