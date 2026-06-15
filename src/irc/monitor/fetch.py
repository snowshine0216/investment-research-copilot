"""EDGE: narrow NAV prefetch for the 7 monitor funds.

Fetches NAV history via `fetch_fund_nav_history` (indicator 単位净値走势) only.
`基金概况` is NEVER used here (grep acceptance test enforces it repo-wide).

On failure (network error, empty result) returns None — the factor eligibility
gate in signal.py surfaces the gap as trend → N/A (reason: trend_insufficient_history
if len < minimum_observations; or factor simply marked ineligible/absent).

Index-valuation prefetch: in v1 the monitor reads CACHED index valuation through
the same `_index_valuation_metrics` path the opportunity stage uses (Task 30 reads
from DuckDB). A dedicated live prefetch is only needed if the cache is empty; if
so, ship valuation → N/A (reason: valuation_no_anchor). No additional code needed.
# TODO(post-v1): optional narrow index-valuation refresh if cache miss at runtime.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from irc.data.akshare_client import fetch_fund_nav_history

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavFetchResult:
    fund_id: str
    latest_nav: float
    as_of_date: str
    acc_series: tuple[tuple[str, float], ...]  # COALESCE(nav_acc, nav), date-ascending


def _coalesce(row: "pd.Series") -> float:
    """COALESCE(nav_acc, nav): distribution-adjusted accumulative NAV for perf math."""
    acc = row.get("nav_acc")
    if acc is None or pd.isna(acc):
        return float(row["nav"])
    return float(acc)


def nav_series_for(
    fund_id: str,
    *,
    fetch: Callable[[str], pd.DataFrame] = fetch_fund_nav_history,
) -> NavFetchResult | None:
    """EDGE: fetch one fund's NAV history → acc-series (distribution-safe).

    Returns None on fetch failure or empty result — the factor eligibility gate
    surfaces the gap as trend/valuation N/A rather than crashing the brief.
    """
    try:
        df = fetch(fund_id)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("NAV fetch failed for %s", fund_id, exc_info=True)
        return None
    if df is None or df.empty:
        return None
    df = df.sort_values("date")
    series = tuple((str(r["date"]), _coalesce(r)) for _, r in df.iterrows())
    last = df.iloc[-1]
    return NavFetchResult(
        fund_id=fund_id,
        latest_nav=float(last["nav"]),
        as_of_date=str(last["date"]),
        acc_series=series,
    )
