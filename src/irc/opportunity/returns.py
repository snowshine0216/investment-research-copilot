from __future__ import annotations

import math
from typing import TypedDict

import pandas as pd


class RollingReturns(TypedDict):
    ret_1m: float | None
    ret_3m: float | None
    ret_6m: float | None
    ret_12m: float | None


_WINDOWS_BUSINESS_DAYS: dict[str, int] = {
    "ret_1m": 21,
    "ret_3m": 63,
    "ret_6m": 126,
    "ret_12m": 252,
}


def _clean(series: pd.Series) -> pd.Series:
    return series.dropna().astype(float).sort_index()


def rolling_returns(series: pd.Series, *, as_of: pd.Timestamp) -> RollingReturns:
    """Compute return windows relative to `as_of` using positional offsets."""
    s = _clean(series)
    s = s[s.index <= as_of]
    out: RollingReturns = {"ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12m": None}
    if s.empty:
        return out
    latest = float(s.iloc[-1])
    for name, w in _WINDOWS_BUSINESS_DAYS.items():
        if len(s) <= w:
            continue
        anchor = float(s.iloc[-(w + 1)])
        if anchor <= 0 or math.isnan(anchor):
            continue
        out[name] = latest / anchor - 1.0
    return out


def drawdown_since_entry(series: pd.Series, *, entry_date: pd.Timestamp) -> float | None:
    """Peak-to-current drawdown over the post-entry window."""
    s = _clean(series)
    s = s[s.index >= entry_date]
    if s.empty:
        return None
    peak = float(s.cummax().iloc[-1])
    current = float(s.iloc[-1])
    if peak <= 0:
        return None
    return max(0.0, (peak - current) / peak)


def self_history_percentile(series: pd.Series) -> float | None:
    """Rank-based percentile of the latest value within the series.

    Returns None for series with fewer than 30 valid points.

    Uses inclusive (count_le) ranking: a value equal to the historical maximum
    returns 1.0 (100th percentile), not (n-1)/n. This matches the standard
    ECDF definition where ties count at the upper end.
    """
    s = _clean(series)
    if len(s) < 30:
        return None
    latest = float(s.iloc[-1])
    count_le = float((s <= latest).sum())
    return count_le / float(len(s))
