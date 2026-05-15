"""CN constituent data via AkShare.

All public functions degrade failures to empty / None — never raise — so the
snapshot orchestrator can record per-source diagnostics without crashing.

The `_ak_call` indirection lets tests mock akshare cleanly (same pattern as
`irc.data.akshare_client`)."""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any

import pandas as pd

from irc.fundamentals.types import BrokerReport, Constituent, FilingDigest


_SINA_FINSUMMARY_URL = (
    "https://vip.stock.finance.sina.com.cn/corp/go.php/"
    "vFD_FinanceSummary/stockid/{symbol}.phtml"
)


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _today_iso() -> str:
    """Indirection for tests; returns today's date in ISO format."""
    return date.today().isoformat()


def _current_year() -> str:
    return str(date.today().year)


def _suffix_for_code(code: str) -> str:
    """Map a 6-digit CN ticker to its exchange suffix. SH for codes starting
    with 5/6 (Shanghai), SZ for everything else (Shenzhen)."""
    return "SH" if code[:1] in ("5", "6") else "SZ"


def _to_qualified_symbol(code: str) -> str:
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{_suffix_for_code(code)}"


def fetch_cn_index_constituents(
    index_code: str,
    *,
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Top-N constituents of a CN index by weight (CSI Index source).

    Weight in the CSI feed is percent (e.g. 5.12 = 5.12%); we normalize to a
    fraction. Returns empty tuple on failure."""
    try:
        df = _ak_call("index_stock_cons_weight_csindex", symbol=index_code)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
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


def fetch_cn_etf_holdings(
    symbol: str,
    *,
    as_of: str = "",
    top_n: int = 10,
) -> tuple[Constituent, ...]:
    """Latest disclosed holdings for a CN ETF. Falls back to the current year
    when `as_of` is empty. Returns empty tuple on failure."""
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


def fetch_cn_broker_reports(
    symbol: str,
    *,
    days: int = 90,
    max_reports: int = 20,
) -> tuple[BrokerReport, ...]:
    """Recent 券商研报 for a CN stock, newest first.

    Filters to reports published within `days` days of today. The EastMoney
    feed does not carry an explicit target_price, so it stays None.
    """
    try:
        df = _ak_call("stock_research_report_em", symbol=symbol)
    except Exception:
        return ()
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    needed = {"机构", "东财评级", "报告名称", "日期"}
    if not needed.issubset(df.columns):
        return ()
    cutoff = pd.Timestamp(_today_iso()) - pd.Timedelta(days=days)
    parsed_dates = pd.to_datetime(df["日期"], errors="coerce")
    fresh = df.assign(_date=parsed_dates).dropna(subset=["_date"])
    fresh = fresh[fresh["_date"] >= cutoff].sort_values("_date", ascending=False)
    qualified = _to_qualified_symbol(symbol)
    out: list[BrokerReport] = []
    for _, row in fresh.head(max_reports).iterrows():
        out.append(
            BrokerReport(
                symbol=qualified,
                broker=str(row.get("机构", "") or ""),
                rating=str(row.get("东财评级", "") or ""),
                target_price=None,
                published_iso=row["_date"].strftime("%Y-%m-%d"),
                title=str(row.get("报告名称", "") or ""),
                source_url=str(row.get("报告PDF链接", "") or ""),
            )
        )
    return tuple(out)


_KEY_REVENUE = "营业总收入"
_KEY_NET_INCOME = "归母净利润"
_KEY_COST = "营业成本"


def _yyyymmdd_to_period(label: str) -> tuple[str, str]:
    """Map a 'YYYYMMDD' column header to (fiscal_period, filed_at_iso).

    1231 → '<YYYY>FY', 0331 → '<YYYY>Q1', 0630 → 'Q2', 0930 → 'Q3'.
    """
    year, mmdd = label[:4], label[4:]
    quarter_map = {"0331": "Q1", "0630": "Q2", "0930": "Q3"}
    period = f"{year}FY" if mmdd == "1231" else f"{year}{quarter_map.get(mmdd, '')}"
    filed = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
    return period, filed


def _common_metric(df: pd.DataFrame, name: str, col: str) -> float | None:
    matches = df[(df.get("选项") == "常用指标") & (df.get("指标") == name)]
    if matches.empty or col not in matches.columns:
        return None
    raw = matches.iloc[0][col]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    return value


def fetch_cn_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest 季报 / 年报 digest derived from `stock_financial_abstract`.

    Returns None on failure or when the core metrics (revenue, net income, cost)
    are missing for the latest reporting period.
    """
    try:
        df = _ak_call("stock_financial_abstract", symbol=symbol)
    except Exception:
        return None
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    period_cols = [
        c for c in df.columns
        if isinstance(c, str) and len(c) == 8 and c.isdigit()
    ]
    if not period_cols:
        return None
    latest = sorted(period_cols, reverse=True)[0]
    revenue = _common_metric(df, _KEY_REVENUE, latest)
    net_income = _common_metric(df, _KEY_NET_INCOME, latest)
    cost = _common_metric(df, _KEY_COST, latest)
    if revenue is None or net_income is None or cost is None:
        return None
    prior_label = f"{int(latest[:4]) - 1}{latest[4:]}"
    prior_revenue = _common_metric(df, _KEY_REVENUE, prior_label)
    prior_net_income = _common_metric(df, _KEY_NET_INCOME, prior_label)
    revenue_yoy = (revenue - prior_revenue) / prior_revenue if prior_revenue else None
    net_income_yoy = (
        (net_income - prior_net_income) / prior_net_income
        if prior_net_income
        else None
    )
    gross_margin = 1 - (cost / revenue) if revenue else None
    period, filed = _yyyymmdd_to_period(latest)
    return FilingDigest(
        symbol=_to_qualified_symbol(symbol),
        fiscal_period=period,
        filed_at_iso=filed,
        revenue_yoy=revenue_yoy,
        net_income_yoy=net_income_yoy,
        gross_margin=gross_margin,
        source_url=_SINA_FINSUMMARY_URL.format(symbol=str(symbol).strip()),
    )
