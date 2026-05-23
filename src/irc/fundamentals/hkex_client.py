"""HKEX adapter.

Uses EastMoney's HK income-statement endpoint (`stock_financial_hk_report_em`)
via the same `_ak_call` indirection as the CN AkShare client. Long-format input
(REPORT_DATE / STD_ITEM_NAME / AMOUNT) gets pivoted in-memory to extract
revenue, net income, and gross profit for the latest period and the same period
one year earlier.

Returns None on any failure; the snapshot orchestrator records the diagnostic.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from irc.fundamentals.types import FilingDigest, NewsItem


_KEY_REVENUE = "营业额"
_KEY_NET_INCOME = "股东应占溢利"
_KEY_GROSS_PROFIT = "毛利"
_EM_HK_QUOTE_URL = "https://emweb.securities.eastmoney.com/PC_HKF10/pages/home/index.html?code={symbol}#/cwfx"


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection so tests can patch akshare cleanly."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _normalize_hk_code(symbol: str) -> str:
    """Strip '.HK' suffix and zero-pad to 5 digits — EastMoney's HK endpoints expect '00700'."""
    digits = "".join(ch for ch in str(symbol) if ch.isdigit())
    return digits.zfill(5) if digits else ""


def _to_qualified_hk_symbol(symbol: str) -> str:
    code = _normalize_hk_code(symbol)
    return f"{code[1:]}.HK" if code.startswith("0") and len(code) == 5 else f"{code}.HK"


def _period_label(report_iso: str, start_iso: str) -> str:
    """Infer fiscal period from (REPORT_DATE - START_DATE). 12-31 → FY, else Q1/Q2/Q3."""
    try:
        end = pd.Timestamp(report_iso)
        start = pd.Timestamp(start_iso)
    except (ValueError, TypeError):
        return ""
    year = end.year
    if end.month == 12 and end.day == 31 and start.month == 1:
        return f"{year}FY"
    days = (end - start).days + 1
    if days <= 100:
        return f"{year}Q1"
    if days <= 200:
        return f"{year}Q2"
    if days <= 290:
        return f"{year}Q3"
    return f"{year}FY"


def _amount_for(df: pd.DataFrame, report_date: str, item: str) -> float | None:
    matches = df[(df["REPORT_DATE"] == report_date) & (df["STD_ITEM_NAME"] == item)]
    if matches.empty:
        return None
    try:
        return float(matches.iloc[0]["AMOUNT"])
    except (TypeError, ValueError):
        return None


def fetch_hk_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest interim / annual digest for a HK-listed company. Returns None on failure."""
    code = _normalize_hk_code(symbol)
    if not code:
        return None
    try:
        df = _ak_call(
            "stock_financial_hk_report_em",
            stock=code, symbol="利润表", indicator="报告期",
        )
    except Exception:
        return None
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if not {"REPORT_DATE", "STD_ITEM_NAME", "AMOUNT", "START_DATE"}.issubset(df.columns):
        return None
    revenue_rows = df[df["STD_ITEM_NAME"] == _KEY_REVENUE]
    if revenue_rows.empty:
        return None
    latest_report = revenue_rows.sort_values("REPORT_DATE", ascending=False).iloc[0]
    report_date = latest_report["REPORT_DATE"]
    start_date = latest_report["START_DATE"]
    revenue = _amount_for(df, report_date, _KEY_REVENUE)
    net_income = _amount_for(df, report_date, _KEY_NET_INCOME)
    gross_profit = _amount_for(df, report_date, _KEY_GROSS_PROFIT)
    if revenue is None:
        return None

    end_ts = pd.Timestamp(report_date)
    prior_target = end_ts - pd.DateOffset(years=1)
    prior_rows = revenue_rows[
        pd.to_datetime(revenue_rows["REPORT_DATE"]) == prior_target
    ]
    if not prior_rows.empty:
        prior_report_date = prior_rows.iloc[0]["REPORT_DATE"]
        prior_revenue = _amount_for(df, prior_report_date, _KEY_REVENUE)
        prior_net = _amount_for(df, prior_report_date, _KEY_NET_INCOME)
    else:
        prior_revenue = prior_net = None

    revenue_yoy = (revenue - prior_revenue) / prior_revenue if prior_revenue else None
    net_income_yoy = (
        (net_income - prior_net) / prior_net
        if net_income is not None and prior_net
        else None
    )
    gross_margin = gross_profit / revenue if gross_profit is not None and revenue else None

    filed_iso = end_ts.strftime("%Y-%m-%d")
    return FilingDigest(
        symbol=_to_qualified_hk_symbol(symbol),
        fiscal_period=_period_label(report_date, start_date),
        filed_at_iso=filed_iso,
        revenue_yoy=revenue_yoy,
        net_income_yoy=net_income_yoy,
        gross_margin=gross_margin,
        source_url=_EM_HK_QUOTE_URL.format(symbol=code),
    )


# ── Item 003: HK stock news ───────────────────────────────────────────────────

def fetch_hk_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]:
    """Top-K recent HK stock news via AkShare `stock_hk_news_em`.

    P1-c: exceptions propagate to the caller (snapshot.py catches them as
    hk_news_fetch_failed). Returns () only on empty/malformed DataFrame.
    The caller uses hk_news_adapter_available() to distinguish "adapter missing"
    from "runtime exception" — do NOT call this function when the adapter is absent.
    """
    code = _normalize_hk_code(stock)
    if not code:
        return ()
    df = _ak_call("stock_hk_news_em", symbol=code)
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    title_col = "标题" if "标题" in df.columns else None
    date_col = "发布时间" if "发布时间" in df.columns else None
    url_col = "新闻链接" if "新闻链接" in df.columns else None
    summary_col = "内容摘要" if "内容摘要" in df.columns else None
    if not (title_col and date_col):
        return ()
    sorted_df = df.sort_values(date_col, ascending=False).head(top_k)
    out: list[NewsItem] = []
    for _, row in sorted_df.iterrows():
        raw_date = str(row[date_col])
        published = raw_date.split(" ")[0]
        out.append(NewsItem(
            symbol=code,
            title=str(row[title_col]),
            url=str(row[url_col]) if url_col else "",
            published_iso=published,
            summary=str(row[summary_col]) if summary_col else "",
            source="stock_hk_news_em",
        ))
    return tuple(out)


def hk_news_adapter_available() -> bool:
    """Return True iff the installed AkShare exposes `stock_hk_news_em`.

    Lazy-imports AkShare; on ImportError returns False.
    """
    try:
        import akshare as ak  # local import
    except ImportError:
        return False
    return hasattr(ak, "stock_hk_news_em")
