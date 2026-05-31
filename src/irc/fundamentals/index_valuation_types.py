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
