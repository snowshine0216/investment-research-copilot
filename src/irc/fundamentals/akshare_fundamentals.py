"""CN constituent data via AkShare.

Public functions: `fetch_cn_index_constituents`, `fetch_cn_etf_holdings`.
Filing and broker-report fetchers live in `akshare_filing` (re-exported here).

All public functions degrade failures to empty / None — never raise — so the
snapshot orchestrator can record per-source diagnostics without crashing.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.types import Constituent


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _current_year() -> str:
    return str(date.today().year)


def _suffix_for_code(code: str) -> str:
    """SH for codes starting with 5/6 (Shanghai), SZ for everything else."""
    return "SH" if code[:1] in ("5", "6") else "SZ"


def _to_qualified_symbol(code: str) -> str:
    code = str(code).strip().upper()
    if "." in code:
        return code
    if len(code) > 2 and code[:2] in ("SZ", "SH"):
        code = code[2:]
    return f"{code}.{_suffix_for_code(code)}"


def _sina_index_symbol(index_code: str) -> str | None:
    """Map a numeric CN index code to the format accepted by Sina endpoint.

    AkShare's `index_stock_cons_sina` currently resolves CN indices from plain
    numeric codes (e.g. `399006`) and returns empty frames for prefixed forms
    like `sz399006` / `sh000300`.
    """
    if not index_code:
        return None
    head = index_code[:1]
    if head in ("0", "3", "5", "6"):
        return index_code
    return None


def _parse_csindex_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    needed = {"成分券代码", "成分券名称", "权重"}
    if not needed.issubset(df.columns):
        return ()
    ranked = df.sort_values("权重", ascending=False).head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row["成分券代码"])),
            name=str(row["成分券名称"]),
            weight=float(row["权重"]) / 100,
            market="cn",
        )
        for _, row in ranked.iterrows()
    )


def _parse_sina_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    """Sina returns columns "品种代码" / "品种名称" with NO weight.

    Equal-weight (weight=0.0) is acceptable downstream: the thesis classifier
    counts YoY signs across constituents, never multiplies by weight.
    """
    code_col = ""
    name_col = ""
    if {"品种代码", "品种名称"}.issubset(df.columns):
        code_col, name_col = "品种代码", "品种名称"
    elif {"symbol", "name"}.issubset(df.columns):
        # Current AkShare schema for index_stock_cons_sina.
        code_col, name_col = "symbol", "name"
    else:
        return ()
    head = df.head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row[code_col])),
            name=str(row[name_col]),
            weight=0.0,
            market="cn",
        )
        for _, row in head.iterrows()
    )


def fetch_cn_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N constituents of a CN index by weight.

    Primary source is CSI (`index_stock_cons_weight_csindex`), which only
    publishes 中证指数公司 indices (000xxx, 930xxx, 000688). For SZSE codes
    (399xxx) and any other code CSI does not cover, fall back to Sina
    (`index_stock_cons_sina`) and return equal-weight (weight=0.0) entries.
    """
    try:
        df = _ak_call("index_stock_cons_weight_csindex", symbol=index_code)
    except Exception:
        df = pd.DataFrame()
    if isinstance(df, pd.DataFrame) and not df.empty:
        parsed = _parse_csindex_frame(df, top_n)
        if parsed:
            return parsed
    sina_symbol = _sina_index_symbol(index_code)
    if sina_symbol is None:
        return ()
    try:
        df2 = _ak_call("index_stock_cons_sina", symbol=sina_symbol)
    except Exception:
        return ()
    if not isinstance(df2, pd.DataFrame) or df2.empty:
        return ()
    return _parse_sina_frame(df2, top_n)


def fetch_cn_etf_holdings(
    symbol: str,
    *,
    as_of: str = "",
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Latest disclosed holdings for a CN ETF."""
    year = as_of or _current_year()
    try:
        df = _ak_call("fund_portfolio_hold_em", symbol=symbol, date=year)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    needed = {"股票代码", "股票名称", "占净值比例", "季度"}
    if not needed.issubset(df.columns):
        return ()
    latest_quarter = sorted(df["季度"].astype(str).unique())[-1]
    latest = df[df["季度"].astype(str) == latest_quarter]
    ranked = latest.sort_values("占净值比例", ascending=False).head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row["股票代码"])),
            name=str(row["股票名称"]),
            weight=float(row["占净值比例"]) / 100,
            market="cn",
        )
        for _, row in ranked.iterrows()
    )


def _to_qualified_hk_symbol(code: str) -> str:
    """Normalize to 5-digit zero-padded + '.HK' suffix."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return f"{digits.zfill(5)}.HK" if digits else ""


def _parse_hk_index_frame(df: pd.DataFrame, top_n: int) -> tuple[Constituent, ...]:
    """Parse HK index constituent DataFrame from AkShare.
    
    NOTE: AkShare does not currently have a working HK index constituent endpoint.
    The column names below are placeholders based on typical patterns.
    When a real endpoint is discovered, update these column names.
    """
    # Placeholder column names - update when actual AkShare function is discovered
    code_col, name_col, weight_col = "代码", "名称", "权重"
    needed = {code_col, name_col}
    if not needed.issubset(df.columns):
        return ()
    has_weight = weight_col in df.columns
    if has_weight:
        df = df.sort_values(weight_col, ascending=False)
    head = df.head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_hk_symbol(row[code_col]),
            name=str(row[name_col]),
            weight=(float(row[weight_col]) / 100) if has_weight else 0.0,
            market="hk",
        )
        for _, row in head.iterrows()
    )


def fetch_hk_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N HK index constituents by weight, market='hk'. Returns () on failure.
    
    NOTE: AkShare does not currently provide HK index constituent data through
    a standard API. This function is a stub that will return empty results until
    a working endpoint is discovered. When implemented, it should follow the
    pattern of fetch_cn_index_constituents: try a primary source, fall back to
    an alternative if available, and degrade gracefully to () on all failures.
    
    Potential future approaches:
    - Wait for AkShare to add stock_hk_index_constituent_em or similar
    - Use alternative data sources (HKEX, Bloomberg, manual data files)
    - Create a hardcoded mapping for major indices (HSI, HSTECH, etc.)
    """
    try:
        # Placeholder: No working AkShare function exists yet
        # When discovered, replace "PLACEHOLDER_FUNCTION" with actual function name
        df = _ak_call("PLACEHOLDER_FUNCTION", symbol=index_code)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    return _parse_hk_index_frame(df, top_n)


# Re-exports removed — import fetch_cn_broker_reports / fetch_cn_filing_digest
# from irc.fundamentals.akshare_filing directly.
