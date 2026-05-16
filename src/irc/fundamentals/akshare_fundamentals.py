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
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{_suffix_for_code(code)}"


def _sina_index_symbol(index_code: str) -> str | None:
    """Map a numeric CN index code to its Sina-prefixed symbol.

    Leading 6/5 → Shanghai (`sh`); leading 3/0 → Shenzhen (`sz`).
    Codes whose first character is not in {0,3,5,6} return None so the caller
    can short-circuit without an AkShare round-trip.
    """
    if not index_code:
        return None
    head = index_code[:1]
    if head in ("6", "5"):
        return f"sh{index_code}"
    if head in ("3", "0"):
        return f"sz{index_code}"
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
    needed = {"品种代码", "品种名称"}
    if not needed.issubset(df.columns):
        return ()
    head = df.head(top_n)
    return tuple(
        Constituent(
            symbol=_to_qualified_symbol(str(row["品种代码"])),
            name=str(row["品种名称"]),
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


# Re-exports removed — import fetch_cn_broker_reports / fetch_cn_filing_digest
# from irc.fundamentals.akshare_filing directly.
