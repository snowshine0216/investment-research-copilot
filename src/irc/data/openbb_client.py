from __future__ import annotations

from typing import Any

import pandas as pd

OPENBB_PROVIDER_DEFAULT = "yfinance"


def _call_obb(path: str, **kwargs: Any) -> Any:
    """Indirection so tests can mock without touching the heavy openbb import."""
    from openbb import obb  # local import; openbb is heavy
    node: Any = obb
    for part in path.split("."):
        node = getattr(node, part)
    return node(**kwargs)


def fetch_etf_price_history(
    ticker: str,
    start: str,
    end: str,
    provider: str = OPENBB_PROVIDER_DEFAULT,
) -> pd.DataFrame:
    """Fetch daily OHLCV via OpenBB. Returns DataFrame with columns: date, open, high, low, close, volume."""
    obj = _call_obb(
        "equity.price.historical",
        symbol=ticker, start_date=start, end_date=end, provider=provider,
    )
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    return df[["date", "open", "high", "low", "close", "volume"]].copy()


def fetch_macro_series(series_id: str, start: str, end: str) -> pd.DataFrame:
    """Fetch a FRED-style macro series. Returns DataFrame with columns: date, value."""
    obj = _call_obb(
        "economy.fred_series",
        symbol=series_id, start_date=start, end_date=end,
    )
    df = obj.to_df()
    df = df.reset_index() if df.index.name in ("date", "Date") else df
    if "value" not in df.columns and series_id in df.columns:
        df = df.rename(columns={series_id: "value"})
    return df[["date", "value"]].copy()
