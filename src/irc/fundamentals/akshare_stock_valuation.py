"""Per-stock PE/PB valuation fetcher (Phase D PR1) via EastMoney `stock_value_em`.

`stock_value_em(symbol="<6-digit>")` returns the full daily history with
columns `数据日期` (date), `PE(TTM)`, `市净率` (PB), plus 总市值/PEG/etc. One call
returns ~2000+ trading days — ample for the 120/180 maturity gate. Free, no
token, A-share only, routed through IRC_CN_PROXY when set (D2), else CN-direct.

`dividend_yield` is left None: EastMoney exposes no per-stock dividend yield
(mirrors the index fetcher; the column stays nullable). Degrade-to-None
contract: adapter raise / empty frame / no parseable dates → None, never raises.

EXACT column strings are pinned by the gate-#4 live test
(`tests/fundamentals/test_stock_valuation_live.py`) — authored, not run here.
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any

import pandas as pd

from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)
from irc.http_proxy import AKSHARE_PROXY_LOCK, proxy_env, resolve_cn_proxy

_log = logging.getLogger(__name__)

_PE_COL: str = "PE(TTM)"
_PB_COL: str = "市净率"
_DATE_COL: str = "数据日期"


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import

    return getattr(ak, fn_name)(**kwargs)


def _coerce(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(value) else value


def _series_maps(
    df: pd.DataFrame,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Pure: map each parseable 数据日期 to its PE(TTM) and 市净率 value."""
    if not isinstance(df, pd.DataFrame) or df.empty or _DATE_COL not in df.columns:
        return {}, {}
    parsed = pd.to_datetime(df[_DATE_COL], errors="coerce")
    pe_raw = df[_PE_COL] if _PE_COL in df.columns else [None] * len(df)
    pb_raw = df[_PB_COL] if _PB_COL in df.columns else [None] * len(df)
    pe_map: dict[str, float | None] = {}
    pb_map: dict[str, float | None] = {}
    for d, pe, pb in zip(parsed, pe_raw, pb_raw, strict=True):
        if pd.isna(d):
            continue
        iso = d.date().isoformat()
        pe_map[iso] = _coerce(pe)
        pb_map[iso] = _coerce(pb)
    return pe_map, pb_map


def _fetch_frame(symbol: str) -> pd.DataFrame | None:
    proxy = resolve_cn_proxy()
    ctx = proxy_env(proxy) if proxy else contextlib.nullcontext()
    try:
        # proxy_env mutates the process-global env; lock to avoid cross-thread
        # bleed with other proxy_env callers (mirrors akshare_client's DXY path).
        with AKSHARE_PROXY_LOCK:
            with ctx:
                df = _ak_call("stock_value_em", symbol=symbol)
    except Exception as exc:
        _log.warning("stock_value_em(%r) failed: %s: %s", symbol, type(exc).__name__, exc)
        return None
    if not isinstance(df, pd.DataFrame):
        _log.warning(
            "stock_value_em(%r) returned unexpected type %s", symbol, type(df).__name__
        )
        return pd.DataFrame()
    return df


def fetch_stock_valuation_history(stock_code: str) -> StockValuationHistory | None:
    """Full PE/PB series for an A-share via EastMoney; None on miss/empty/raise.
    AkShare-only ingest infra — NOT a provider method."""
    df = _fetch_frame(stock_code)
    if df is None:
        return None
    pe_map, pb_map = _series_maps(df)
    dates = sorted(set(pe_map) | set(pb_map))
    if not dates:
        return None
    rows = tuple(
        StockValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=pb_map.get(d),
            dividend_yield=None,
        )
        for d in dates
    )
    return StockValuationHistory(stock_code=stock_code, rows=rows)
