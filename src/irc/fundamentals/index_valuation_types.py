"""Index-level valuation snapshot type (item 001).

Frozen, immutable. All metric fields are `float | None` — every fetch path
degrades to None on failure / missing column, never raises.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexValuation:
    index_key: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    as_of_iso: str


@dataclass(frozen=True)
class IndexValuationPoint:
    """One dated index-valuation observation (full history, item 001 Phase 1)."""
    date_iso: str
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None


@dataclass(frozen=True)
class IndexValuationHistory:
    """Full PE/PB/dividend series for one broad index. Degrades to None at the
    fetch edge (unknown key / adapter failure / empty frame), never raises."""
    index_key: str
    rows: tuple[IndexValuationPoint, ...]
