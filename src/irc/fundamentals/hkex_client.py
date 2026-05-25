"""HKEX adapter.

Uses EastMoney's HK income-statement endpoint (`stock_financial_hk_report_em`)
via the same `_ak_call` indirection as the CN AkShare client. Long-format input
(REPORT_DATE / STD_ITEM_NAME / AMOUNT) gets pivoted in-memory to extract
revenue, net income, and gross profit for the latest period and the same period
one year earlier.

Returns None on any failure; the snapshot orchestrator records the diagnostic.
"""
from __future__ import annotations

import re
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

_EASTMONEY_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
_EM_HIGHLIGHT_RE = re.compile(r"</?em>|　")


def _strip_em_highlights(text: str) -> str:
    """Remove `<em>…</em>` highlight markup and `\\u3000` (ideographic space)
    without invoking pyarrow's RE2 engine (which rejects `\\u` escapes)."""
    if not text:
        return ""
    return _EM_HIGHLIGHT_RE.sub("", text)


def _fetch_eastmoney_news_direct(
    symbol: str, *, page_size: int = 10, timeout: float = 10.0,
) -> tuple[dict, ...]:
    """Direct EastMoney search-API call — works for HK codes (e.g. `00700`).

    Used because (a) the installed AkShare lacks `stock_hk_news_em`, and (b)
    the EastMoney search endpoint accepts HK 5-digit codes directly and
    returns the same article shape used by `stock_news_em` for CN codes.
    """
    import json as _json

    import requests as _requests  # local import — adapter boundary

    inner = {
        "uid": "", "keyword": symbol,
        "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": page_size,
            "preTag": "<em>", "postTag": "</em>",
        }},
    }
    params = {
        "cb": "cb",
        "param": _json.dumps(inner, ensure_ascii=False),
        "_": "1",
    }
    headers = {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        ),
        "accept": "*/*",
        "referer": f"https://so.eastmoney.com/news/s?keyword={symbol}",
    }
    resp = _requests.get(_EASTMONEY_NEWS_URL, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    m = re.match(r"^cb\((.*)\)$", resp.text.strip(), re.S)
    if not m:
        return ()
    data = _json.loads(m.group(1))
    return tuple(data.get("result", {}).get("cmsArticleWebOld", []) or ())


def fetch_hk_stock_news(stock: str, *, top_k: int = 3) -> tuple[NewsItem, ...]:
    """Top-K recent HK stock news from EastMoney.

    Primary: AkShare's `stock_hk_news_em` (mockable in tests). Fallback:
    direct EastMoney JSONP call (`_fetch_eastmoney_news_direct`) —
    required because the installed AkShare doesn't expose
    `stock_hk_news_em`. Exceptions from the fallback propagate so callers
    tag the holding as `hk_news_fetch_failed` (P1-c contract).
    """
    code = _normalize_hk_code(stock)
    if not code:
        return ()
    try:
        df = _ak_call("stock_hk_news_em", symbol=code)
    except Exception:
        articles = _fetch_eastmoney_news_direct(code, page_size=max(top_k, 10))
        sorted_articles = sorted(
            articles, key=lambda a: a.get("date", ""), reverse=True,
        )[:top_k]
        return tuple(
            NewsItem(
                symbol=code,
                title=_strip_em_highlights(str(a.get("title", ""))),
                url=str(a.get("url", "")),
                published_iso=str(a.get("date", "")).split(" ")[0],
                summary=_strip_em_highlights(str(a.get("content", ""))),
                source="eastmoney_direct",
            )
            for a in sorted_articles
        )
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
    """Always True: `fetch_hk_stock_news` has an EastMoney-direct fallback
    that works even when AkShare lacks `stock_hk_news_em`."""
    return True
