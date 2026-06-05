"""Index-level PE/PB valuation fetcher (item 001) via legulegu AkShare endpoints.

`stock_index_pe_lg` (PE) and `stock_index_pb_lg` (PB) are addressed by a
live-confirmed Chinese broad-index symbol from `_LEGULEGU_INDEX_SYMBOL`. Network
I/O is confined to the `_ak_call` indirection; extraction is a pure helper.

Degrade-to-None contract: unknown index_key → None; any adapter failure or
empty frame → metrics None (never raises). Matches `fetch_cn_filing_digest`.

NOTE: legulegu PE/PB endpoints carry no dividend-yield column, so
`dividend_yield` is None in practice (spec §Judgment call 3). The forbidden
fund-profile indicator is never used here (see test_static_profile_invariant).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.index_valuation_types import (
    IndexValuation,
    IndexValuationHistory,
    IndexValuationPoint,
)

# Production allowlist — live-confirmed exact legulegu symbols ONLY (D2). The
# display/symbol coupling to _BROAD_INDEX_DISPLAY is removed: production fetch
# resolves symbols HERE, never from the display map.
_LEGULEGU_INDEX_SYMBOL: dict[str, str] = {
    "csi300": "沪深300",
    "csi500": "中证500",
    "csi1000": "中证1000",
    "sse50": "上证50",
}

# Speculative symbols — clearly marked, NOT consulted by production fetch/ingest.
# Only the gated live sweep probes these (D2). Graduating one moves it UP into
# _LEGULEGU_INDEX_SYMBOL (and the live hard-assert set) in a follow-up PR.
_SPECULATIVE_LEGULEGU_SYMBOL: dict[str, str] = {
    "star50": "科创50",
    "chinext": "创业板指",
    "chinext50": "创业板50",
    "csi_dividend": "中证红利",
    "csi_dividend_lc": "中证红利低波",
    "csi_a500": "中证A500",
}

# Dedicated legulegu columns (D1). PE reads 滚动市盈率 (rolling/TTM) ONLY — never
# falls back to 静态市盈率 (ADR 0012 requires PE-TTM). PB reads the cap-weighted
# 市净率, NOT the 等权市净率 equal-weight variant.
_LEGULEGU_PE_TTM_COL: str = "滚动市盈率"
_LEGULEGU_PB_COL: str = "市净率"
_DIV_COLS: tuple[str, ...] = ("股息率", "股息率%", "dividend_yield")
_DATE_COLS: tuple[str, ...] = ("日期", "date", "trade_date")

# §2.3 csindex canonical PE column. CSI publishes 市盈率1 = total mkt-cap ÷ TTM
# attributable net profit (PE-TTM/trailing); 市盈率2 is static/LYR. This is a
# DEDICATED constant — csindex column names are NOT in the legulegu _PE_COLS set,
# so this fetcher must not reuse _series_map(..., _PE_COLS).
_CSINDEX_PE_TTM_COL: str = "市盈率1"

# Sector slug -> CSI index code (csindex `stock_zh_index_value_csindex` symbol).
# 930708 confirmed live for 中证有色金属; the other two are best-effort,
# confirmed by the gated live test (degrade-to-None on miss).
_SECTOR_INDEX_CODE: dict[str, str] = {
    "csi_nonferrous": "930708",
    "csi_resource": "000819",
    "csi_nonferrous_mining": "931892",
}


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _today_iso() -> str:
    return date.today().isoformat()


def _latest_row(df: pd.DataFrame) -> pd.Series | None:
    """Return the row with the latest date, or the last row if no date column."""
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if date_col is None:
        return df.iloc[-1]
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    ordered = df.assign(_d=parsed).dropna(subset=["_d"]).sort_values("_d")
    if ordered.empty:
        return None
    return ordered.iloc[-1]


def _extract_latest_value(
    df: pd.DataFrame, candidate_cols: tuple[str, ...]
) -> float | None:
    """Pure: pick the latest-date row, read the first matching column, coerce."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    col = next((c for c in candidate_cols if c in df.columns), None)
    if col is None:
        return None
    row = _latest_row(df)
    if row is None:
        return None
    try:
        value = float(row[col])
    except (TypeError, ValueError):
        return None
    return None if pd.isna(value) else value


def _fetch_frame(fn_name: str, cn_name: str) -> pd.DataFrame | None:
    """Return DataFrame on success, None on adapter exception (distinguishes from empty)."""
    try:
        df = _ak_call(fn_name, symbol=cn_name)
    except Exception:
        return None
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _series_map(df: pd.DataFrame, candidate_cols: tuple[str, ...]) -> dict[str, float | None]:
    """Pure: map each parseable date to the first matching metric column value.

    Unknown/missing column or empty frame → empty map. Non-coercible cells → None
    for that date. Date parsing mirrors `_latest_row`'s `_DATE_COLS` precedence.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    col = next((c for c in candidate_cols if c in df.columns), None)
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if col is None or date_col is None:
        return {}
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    out: dict[str, float | None] = {}
    for d, raw in zip(parsed, df[col], strict=True):
        if pd.isna(d):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None
        if value is not None and pd.isna(value):
            value = None
        out[d.date().isoformat()] = value
    return out


def fetch_cn_index_valuation_history(index_key: str) -> IndexValuationHistory | None:
    """Full PE/PB series for a recognised broad index; None for unknown keys or
    adapter failure. AkShare-only ingest infra (R4) — NOT a provider method.

    Symbols resolve from the production allowlist ONLY (D2); a speculative slug
    is treated as unknown → None.
    """
    cn_name = _LEGULEGU_INDEX_SYMBOL.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    if pe_df is None and pb_df is None:
        return None
    pe_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), (_LEGULEGU_PE_TTM_COL,))
    pb_map = _series_map(pb_df if pb_df is not None else pd.DataFrame(), (_LEGULEGU_PB_COL,))
    div_map = _series_map(pe_df if pe_df is not None else pd.DataFrame(), _DIV_COLS)
    dates = sorted(set(pe_map) | set(pb_map))
    if not dates:
        return None
    rows = tuple(
        IndexValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=pb_map.get(d),
            dividend_yield=div_map.get(d),
        )
        for d in dates
    )
    return IndexValuationHistory(index_key=index_key, rows=rows)


def _csindex_pe_ttm_map(df: pd.DataFrame) -> dict[str, float | None]:
    """Pure: map each parseable date to its 市盈率1 (PE-TTM) value. Empty map when
    the frame lacks 市盈率1 or a date column. Does NOT consult legulegu _PE_COLS."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    if _CSINDEX_PE_TTM_COL not in df.columns:
        return {}
    date_col = next((c for c in _DATE_COLS if c in df.columns), None)
    if date_col is None:
        return {}
    parsed = pd.to_datetime(df[date_col], errors="coerce")
    out: dict[str, float | None] = {}
    for d, raw in zip(parsed, df[_CSINDEX_PE_TTM_COL], strict=True):
        if pd.isna(d):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None
        if value is not None and pd.isna(value):
            value = None
        out[d.date().isoformat()] = value
    return out


def fetch_cn_sector_index_valuation_history(
    index_key: str,
) -> IndexValuationHistory | None:
    """Full PE-TTM series (from csindex 市盈率1) for a recognised sector index;
    None for unknown slugs / adapter failure / no usable PE rows. pb is always
    None (csindex carries no PB column). AkShare-only ingest infra (R4)."""
    code = _SECTOR_INDEX_CODE.get(index_key)
    if code is None:
        return None
    df = _fetch_frame("stock_zh_index_value_csindex", code)
    if df is None:
        return None
    pe_map = _csindex_pe_ttm_map(df)
    dates = sorted(pe_map)
    if not dates:
        return None
    rows = tuple(
        IndexValuationPoint(
            date_iso=d,
            pe_ttm=pe_map.get(d),
            pb=None,
            dividend_yield=None,
        )
        for d in dates
    )
    return IndexValuationHistory(index_key=index_key, rows=rows)


def fetch_cn_index_valuation(index_key: str) -> IndexValuation | None:
    """PE/PB for a recognised broad index; None for unknown keys or adapter failure.
    Symbols resolve from the production allowlist ONLY (D2)."""
    cn_name = _LEGULEGU_INDEX_SYMBOL.get(index_key)
    if cn_name is None:
        return None
    pe_df = _fetch_frame("stock_index_pe_lg", cn_name)
    pb_df = _fetch_frame("stock_index_pb_lg", cn_name)
    if pe_df is None and pb_df is None:
        return None
    return IndexValuation(
        index_key=index_key,
        pe_ttm=_extract_latest_value(
            pe_df if pe_df is not None else pd.DataFrame(), (_LEGULEGU_PE_TTM_COL,)
        ),
        pb=_extract_latest_value(
            pb_df if pb_df is not None else pd.DataFrame(), (_LEGULEGU_PB_COL,)
        ),
        dividend_yield=_extract_latest_value(
            pe_df if pe_df is not None else pd.DataFrame(), _DIV_COLS
        ),
        as_of_iso=_today_iso(),
    )
