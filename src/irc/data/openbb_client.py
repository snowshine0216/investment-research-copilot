from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from irc.data.akshare_client import (
    fetch_etf_price_history_akshare,
    fetch_macro_series_akshare,
)

_log = logging.getLogger(__name__)

OPENBB_PROVIDER_DEFAULT = "yfinance"

# Series IDs that aren't FRED tickers — skip the OpenBB call and go straight
# to akshare. DXY in particular has no FRED equivalent at the same level
# (DTWEXBGS sits ~120 vs DXY ~98), so OpenBB+FRED would always 404.
_AKSHARE_ONLY_SERIES = frozenset({"DXY"})


def _call_obb(path: str, **kwargs: Any) -> Any:
    """Indirection so tests can mock without touching the heavy openbb import."""
    from openbb import obb  # local import; openbb is heavy
    node: Any = obb
    for part in path.split("."):
        node = getattr(node, part)
    return node(**kwargs)


def _to_yf_symbol(ticker: str) -> str:
    """Map bare 6-digit CN exchange tickers to yfinance symbols.

    Shanghai codes start with 5/6 (e.g. 513500 → 513500.SS); Shenzhen codes
    start with 0/1/2/3 (e.g. 159941 → 159941.SZ). Already-suffixed and
    non-numeric tickers (e.g. VTI, 513500.SS) pass through unchanged."""
    if not ticker.isdigit() or len(ticker) != 6:
        return ticker
    suffix = "SS" if ticker[0] in ("5", "6") else "SZ"
    return f"{ticker}.{suffix}"


def _is_cn_exchange_ticker(ticker: str) -> bool:
    return ticker.isdigit() and len(ticker) == 6


def fetch_etf_price_history(
    ticker: str,
    start: str,
    end: str,
    provider: str = OPENBB_PROVIDER_DEFAULT,
) -> pd.DataFrame:
    """Daily OHLCV. CN exchange tickers (6-digit codes) use akshare's EastMoney
    feed — the canonical, no-auth source; yfinance heavily rate-limits CN ETF
    requests. Other tickers go through OpenBB+yfinance. On primary-source
    failure each path falls back to the other."""
    if _is_cn_exchange_ticker(ticker):
        try:
            return fetch_etf_price_history_akshare(ticker, start, end)
        except Exception as ak_exc:
            _log.warning(
                "akshare price history failed for %s (%s); trying OpenBB+yfinance.",
                ticker, ak_exc,
            )
    try:
        obj = _call_obb(
            "equity.price.historical",
            symbol=_to_yf_symbol(ticker), start_date=start, end_date=end, provider=provider,
        )
    except Exception as obb_exc:
        if _is_cn_exchange_ticker(ticker):
            raise
        _log.warning(
            "OpenBB price history failed for %s (%s); trying akshare fallback.",
            ticker, obb_exc,
        )
        return fetch_etf_price_history_akshare(ticker, start, end)
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_macro_series(series_id: str, start: str, end: str) -> pd.DataFrame:
    """Fetch a macro series. FRED-native IDs try OpenBB+FRED first (needs
    FRED_API_KEY or INTRINIO_API_KEY) and fall back to akshare on failure;
    akshare-only IDs (e.g. DXY) skip OpenBB entirely. Returns DataFrame with
    columns: date, value."""
    if series_id in _AKSHARE_ONLY_SERIES:
        return fetch_macro_series_akshare(series_id, start, end)
    try:
        obj = _call_obb(
            "economy.fred_series",
            symbol=series_id, start_date=start, end_date=end,
        )
    except Exception as openbb_exc:
        _log.warning(
            "OpenBB FRED fetch failed for %s (%s); falling back to akshare.",
            series_id, openbb_exc,
        )
        return fetch_macro_series_akshare(series_id, start, end)
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    if "value" not in df.columns and series_id in df.columns:
        df = df.rename(columns={series_id: "value"})
    return df[["date", "value"]].copy()
