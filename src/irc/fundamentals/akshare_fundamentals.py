"""CN constituent data via AkShare.

Public functions: `fetch_cn_index_constituents`, `fetch_cn_etf_holdings`,
`fetch_cn_stock_news`. Filing and broker-report fetchers live in `akshare_filing`
(re-exported here).

All public functions degrade failures to empty / None — never raise — so the
snapshot orchestrator can record per-source diagnostics without crashing.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from irc.fundamentals.types import Constituent, FundHolding, HoldingsResult, NewsItem


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


# ── Item 003: Exchange parser + quarter column parser ─────────────────────────

_HK_TOKENS: tuple[str, ...] = ("港",)
_US_TOKENS: tuple[str, ...] = ("纽", "纳斯达克", "美")
_SH_TOKENS: tuple[str, ...] = ("沪", "上交所", "上证", "科创板")
_SZ_TOKENS: tuple[str, ...] = ("深", "创业板", "中小板")
_BJ_TOKENS: tuple[str, ...] = ("北", "京")
_QUARTER_END: dict[str, str] = {
    "1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31",
}
_QUARTER_RE = re.compile(r"(\d{4})年(\d)季度")


def _normalize_ticker(raw: str) -> str:
    """Strip `.SH/.SZ/.HK/.US` suffix and leading `sz/sh/bj` (case-insensitive)."""
    code = str(raw).strip()
    code = re.sub(r"\.(SH|SZ|HK|US|BJ)$", "", code, flags=re.IGNORECASE)
    lower = code.lower()
    for prefix in ("sz", "sh", "bj"):
        if lower.startswith(prefix):
            return code[len(prefix):]
    return code


def _parse_exchange_from_market_column(market_value: str) -> str | None:
    """Strategy 1: priority-ordered substring match. None = strategy-1 miss."""
    if not market_value:
        return None
    # Priority: HK / US first to avoid 主板 false-hits.
    for token in _HK_TOKENS:
        if token in market_value:
            return "HK"
    for token in _US_TOKENS:
        if token in market_value:
            return "US"
    # 科创板 must come before generic 沪 because 科创板 trades on Shanghai.
    if "科创板" in market_value:
        return "SH"
    for token in _SH_TOKENS:
        if token in market_value:
            return "SH"
    for token in _SZ_TOKENS:
        if token in market_value:
            return "SZ"
    for token in _BJ_TOKENS:
        if token in market_value:
            return "BJ"
    return None


def _parse_exchange_from_ticker(raw_code: str) -> str:
    """Strategy 2: ticker-prefix routing."""
    upper = str(raw_code).strip().upper()
    if upper.endswith(".HK"):
        return "HK"
    code = _normalize_ticker(raw_code)
    if not code:
        return "UNKNOWN"
    if code.isdigit() and len(code) in (4, 5):
        return "HK"
    if code.isdigit() and len(code) == 6:
        head = code[0]
        if head == "6":
            return "SH"
        if head in ("0", "3"):
            return "SZ"
        if head in ("4", "8"):
            return "BJ"
    if code.isalpha():
        return "US"
    return "UNKNOWN"


def _parse_exchange(row: pd.Series) -> str:
    """Map a holdings row to an exchange code.

    Strategy 1: prefer `股票市场` substring containment (HK/US first).
    Strategy 2: ticker-prefix fallback.
    """
    market = ""
    if "股票市场" in row.index:
        market = str(row["股票市场"] or "").strip()
    if market:
        mapped = _parse_exchange_from_market_column(market)
        if mapped is not None:
            return mapped
    raw = ""
    if "股票代码" in row.index:
        raw = str(row["股票代码"] or "").strip()
    return _parse_exchange_from_ticker(raw)


def _parse_quarter_column(row: pd.Series) -> tuple[str, str]:
    """Return (`source_report_quarter`, `source_report_date`).

    Accepts `季度` or `报告期`. Empty/unparseable → `("", "")`.
    """
    text = ""
    for col in ("季度", "报告期"):
        if col in row.index:
            text = str(row[col] or "")
            if text:
                break
    m = _QUARTER_RE.search(text)
    if m is None:
        return "", ""
    year, q = m.group(1), m.group(2)
    if q not in _QUARTER_END:
        return "", ""
    return f"{year}Q{q}", f"{year}-{_QUARTER_END[q]}"


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
    provider_symbol: str,
    *,
    as_of: str = "",
    top_n: int = 10,
) -> HoldingsResult:
    """Latest disclosed holdings for a CN fund.

    Returns `HoldingsResult` with normalized `FundHolding` rows. Never raises.
    Empty/failed → `HoldingsResult((), "", "")`.
    """
    year = as_of or _current_year()
    try:
        df = _ak_call("fund_portfolio_hold_em", symbol=provider_symbol, date=year)
    except Exception:
        return HoldingsResult((), "", "")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return HoldingsResult((), "", "")
    needed = {"股票代码", "股票名称", "占净值比例"}
    if not needed.issubset(df.columns):
        return HoldingsResult((), "", "")
    # Pick latest quarter via column lex-sort.
    quarter_col = "季度" if "季度" in df.columns else ("报告期" if "报告期" in df.columns else None)
    if quarter_col is None:
        return HoldingsResult((), "", "")
    latest_quarter = sorted(df[quarter_col].astype(str).unique())[-1]
    latest = df[df[quarter_col].astype(str) == latest_quarter]
    ranked = latest.sort_values("占净值比例", ascending=False).head(top_n)
    holdings: list[FundHolding] = []
    for _, row in ranked.iterrows():
        raw_code = str(row["股票代码"]).strip()
        normalized = _normalize_ticker(raw_code)
        exchange = _parse_exchange(row)
        try:
            weight_pct = float(row["占净值比例"])
        except (TypeError, ValueError):
            weight_pct = 0.0
        holdings.append(FundHolding(
            symbol=normalized,
            name_cn=str(row["股票名称"]),
            weight_pct=weight_pct,
            exchange=exchange,
            provider_symbol=raw_code,
        ))
    # Quarter metadata from any latest-quarter row (they share the same text).
    sample = latest.iloc[0]
    quarter_str, date_iso = _parse_quarter_column(sample)
    return HoldingsResult(
        constituents=tuple(holdings),
        source_report_date=date_iso,
        source_report_quarter=quarter_str,
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


def fetch_cn_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]:
    """Top-K most recent stock news items from EastMoney.

    Returns () on adapter exception or empty frame.
    """
    try:
        df = _ak_call("stock_news_em", symbol=stock)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    title_col = "新闻标题" if "新闻标题" in df.columns else None
    date_col = "发布时间" if "发布时间" in df.columns else None
    url_col = "新闻链接" if "新闻链接" in df.columns else None
    summary_col = "新闻内容" if "新闻内容" in df.columns else None
    if not (title_col and date_col):
        return ()
    sorted_df = df.sort_values(date_col, ascending=False).head(top_k)
    out: list[NewsItem] = []
    for _, row in sorted_df.iterrows():
        raw_date = str(row[date_col])
        # "2024-04-15 09:00:00" → "2024-04-15"
        published = raw_date.split(" ")[0]
        out.append(NewsItem(
            symbol=stock,
            title=str(row[title_col]),
            url=str(row[url_col]) if url_col else "",
            published_iso=published,
            summary=str(row[summary_col]) if summary_col else "",
            source="stock_news_em",
        ))
    return tuple(out)


# Re-exports removed — import fetch_cn_broker_reports / fetch_cn_filing_digest
# from irc.fundamentals.akshare_filing directly.
