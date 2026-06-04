"""Per-stock PE/PB Tushare fallback (Phase D PR1) via `daily_basic`.

Fired only on a `stock_value_em` miss/empty. Token-gated (reuses the existing
`.env` TUSHARE_TOKEN plumbing); absent token ⇒ None (no hard failure, the
coverage floor catches shrunk coverage). All network I/O confined to
`_tushare_call` (local `import tushare`); CN-direct, never proxied.

`daily_basic` columns: trade_date, pe_ttm, pb, dv_ratio (dv_ratio is percent →
ratio via /100, mirroring tushare_provider._pct_to_ratio). EXACT columns pinned
by the gate-#4 live test — authored, not run here.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)

_log = logging.getLogger(__name__)

_PE_COLS: tuple[str, ...] = ("pe_ttm", "pe")
_PB_COLS: tuple[str, ...] = ("pb",)
_DIV_COLS: tuple[str, ...] = ("dv_ratio", "dv_ttm")


def _tushare_call(token: str, fn_name: str, **kwargs: Any) -> Any:
    """Network edge (mirrors tushare_provider._tushare_call). Direct, no proxy."""
    import tushare as ts  # local import — never at module load

    pro = ts.pro_api(token)
    return getattr(pro, fn_name)(**kwargs)


def _to_ts_code(symbol: str) -> str:
    code = str(symbol).strip()
    if "." in code:
        return code
    head = code[:1]
    if head in ("5", "6"):
        suffix = "SH"
    elif head in ("4", "8"):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{code}.{suffix}"


def _first_col(df: pd.DataFrame, cols: tuple[str, ...]) -> str | None:
    return next((c for c in cols if c in df.columns), None)


def _coerce_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _pct_to_ratio(value: Any) -> float | None:
    f = _coerce_float(value)
    return None if f is None else f / 100.0


def _iso_from_trade_date(raw: Any) -> str | None:
    s = str(raw)
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def _map_daily_basic(stock_code: str, df: pd.DataFrame) -> StockValuationHistory | None:
    if not isinstance(df, pd.DataFrame) or df.empty or "trade_date" not in df.columns:
        return None
    pe_col = _first_col(df, _PE_COLS)
    pb_col = _first_col(df, _PB_COLS)
    dv_col = _first_col(df, _DIV_COLS)
    ordered = df.sort_values("trade_date")
    rows: list[StockValuationPoint] = []
    for _, row in ordered.iterrows():
        iso = _iso_from_trade_date(row["trade_date"])
        if iso is None:
            continue
        rows.append(StockValuationPoint(
            date_iso=iso,
            pe_ttm=_coerce_float(row[pe_col]) if pe_col else None,
            pb=_coerce_float(row[pb_col]) if pb_col else None,
            dividend_yield=_pct_to_ratio(row[dv_col]) if dv_col else None,
        ))
    if not rows:
        return None
    return StockValuationHistory(stock_code=stock_code, rows=tuple(rows))


def fetch_stock_valuation_history_tushare(
    stock_code: str, *, token: str
) -> StockValuationHistory | None:
    """Tushare daily_basic fallback; None when no token / empty / raise."""
    if not token:
        return None
    ts_code = _to_ts_code(stock_code)
    try:
        df = _tushare_call(token, "daily_basic", ts_code=ts_code)
    except Exception as exc:
        _log.warning(
            "tushare daily_basic(%r) failed: %s: %s", stock_code, type(exc).__name__, exc
        )
        return None
    return _map_daily_basic(stock_code, df)
