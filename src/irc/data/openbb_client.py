from __future__ import annotations

from collections.abc import Callable
import logging
import os
import threading
from typing import Any

import pandas as pd

from irc.data.akshare_client import (
    fetch_etf_price_history_akshare,
    fetch_macro_series_akshare,
)

_log = logging.getLogger(__name__)
_FRED_CRED_LOCK = threading.Lock()  # guards global OBB credential mutation

OPENBB_PROVIDER_DEFAULT = "yfinance"

# Series IDs that aren't FRED tickers — skip the OpenBB call and go straight
# to akshare. DXY has no FRED equivalent at the same level (DTWEXBGS sits
# ~120 vs DXY ~98). CN10Y is akshare-only (FRED's IRLTLT01CNM156N is monthly;
# we want daily for percentile granularity).
_AKSHARE_ONLY_SERIES = frozenset({"DXY", "CN10Y"})


def _call_obb(path: str, **kwargs: Any) -> Any:
    """Indirection so tests can mock without touching the heavy openbb import."""
    from openbb import obb  # local import; openbb is heavy
    node: Any = obb
    for part in path.split("."):
        node = getattr(node, part)
    return node(**kwargs)


def _is_cn_exchange_ticker(ticker: str) -> bool:
    return ticker.isdigit() and len(ticker) == 6


def fetch_etf_price_history(
    ticker: str,
    start: str,
    end: str,
    provider: str = OPENBB_PROVIDER_DEFAULT,
    skip_cn_eastmoney: bool = False,
    on_cn_eastmoney_exhausted: Callable[[], None] | None = None,
) -> pd.DataFrame:
    """Daily OHLCV. CN exchange tickers (6-digit codes) go through akshare
    only — yfinance heavily rate-limits `*.SS`/`*.SZ` symbols and falling
    through to it after akshare failure (a) doesn't help (yfinance can't
    fetch the data either) and (b) burns the shared rate-limit budget across
    every CN ticker in the run. Per-instrument exception handling in
    ingest_cmd skips failed tickers gracefully. Non-CN tickers use OpenBB;
    the akshare fallback is CN-specific and should not mask OpenBB failures."""
    if _is_cn_exchange_ticker(ticker):
        akshare_kwargs: dict[str, Any] = {}
        if skip_cn_eastmoney:
            akshare_kwargs["skip_eastmoney"] = True
        if on_cn_eastmoney_exhausted is not None:
            akshare_kwargs["on_eastmoney_exhausted"] = on_cn_eastmoney_exhausted
        return fetch_etf_price_history_akshare(ticker, start, end, **akshare_kwargs)
    try:
        obj = _call_obb(
            "equity.price.historical",
            symbol=ticker, start_date=start, end_date=end, provider=provider,
        )
    except Exception as obb_exc:
        _log.warning(
            "OpenBB price history failed for %s (%s).",
            ticker, obb_exc,
        )
        raise
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
        fred_key = os.environ.get("FRED_API_KEY")
        if fred_key:
            from openbb import obb  # noqa: PLC0415
            with _FRED_CRED_LOCK:
                obb.user.credentials.fred_api_key = fred_key
                obj = _call_obb(
                    "economy.fred_series",
                    symbol=series_id, start_date=start, end_date=end,
                )
        else:
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
