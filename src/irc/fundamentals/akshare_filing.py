"""CN broker-report and quarterly-filing fetchers via AkShare.

Separated from akshare_fundamentals (constituent fetchers) to keep both files
under 200 lines.
"""
from __future__ import annotations

from datetime import date
import logging
import math
from typing import Any

import pandas as pd

from irc.fundamentals.types import BrokerReport, FilingDigest

_log = logging.getLogger(__name__)


_SINA_FINSUMMARY_URL = (
    "https://vip.stock.finance.sina.com.cn/corp/go.php/"
    "vFD_FinanceSummary/stockid/{symbol}.phtml"
)

_KEY_REVENUE = "营业总收入"
_KEY_NET_INCOME = "归母净利润"
_KEY_COST = "营业成本"
_KEY_ROE = "净资产收益率"


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids importing akshare at module load."""
    import akshare as ak  # local import
    return getattr(ak, fn_name)(**kwargs)


def _suffix_for_code(code: str) -> str:
    return "SH" if code[:1] in ("5", "6") else "SZ"


def _to_qualified_symbol(code: str) -> str:
    code = str(code).strip()
    if "." in code:
        return code
    return f"{code}.{_suffix_for_code(code)}"


def _to_akshare_symbol(symbol: str) -> str:
    return str(symbol).strip().split(".", 1)[0]


def _today_iso() -> str:
    return date.today().isoformat()


def fetch_cn_broker_reports(
    symbol: str,
    *,
    days: int = 90,
    max_reports: int = 20,
) -> tuple[BrokerReport, ...]:
    """Recent 券商研报 for a CN stock, newest first.

    Filters to reports published within `days` days of today.
    """
    akshare_symbol = _to_akshare_symbol(symbol)
    try:
        df = _ak_call("stock_research_report_em", symbol=akshare_symbol)
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
    qualified = _to_qualified_symbol(akshare_symbol)
    out: list[BrokerReport] = []
    for _, row in fresh.head(max_reports).iterrows():
        out.append(BrokerReport(
            symbol=qualified,
            broker=str(row.get("机构", "") or ""),
            rating=str(row.get("东财评级", "") or ""),
            # No 目标价 column in EastMoney's stock_research_report_em
            # (indvAimPriceT/L dropped upstream). Stays None by contract — do
            # NOT fabricate. Consumed by irc.fundamentals.consensus
            # .consensus_upside_pct, which degrades to None. See
            # docs/adr/0009-consensus-upside-degrade-to-none.md.
            target_price=None,
            published_iso=row["_date"].strftime("%Y-%m-%d"),
            title=str(row.get("报告名称", "") or ""),
            source_url=str(row.get("报告PDF链接", "") or ""),
        ))
    return tuple(out)


def _yyyymmdd_to_period(label: str) -> tuple[str, str]:
    """Map 'YYYYMMDD' column header → (fiscal_period, filed_at_iso)."""
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
    return None if math.isnan(value) else value


def _profitability_metric(df: pd.DataFrame, name: str, col: str) -> float | None:
    """Read a 盈利能力-section metric (e.g. 净资产收益率/ROE). Separate from
    _common_metric, which hard-filters 常用指标 (shared by revenue/NI/cost)."""
    matches = df[(df.get("选项") == "盈利能力") & (df.get("指标") == name)]
    if matches.empty or col not in matches.columns:
        # Degrade to None (ROE absence never fails the digest), but DEBUG-log so
        # 盈利能力-section schema drift is observable rather than silent.
        _log.debug(
            "盈利能力 metric %r unavailable in stock_financial_abstract "
            "(section/metric absent or column %r missing)", name, col,
        )
        return None
    raw = matches.iloc[0][col]
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def fetch_cn_filing_digest(symbol: str) -> FilingDigest | None:
    """Latest 季报/年报 digest from `stock_financial_abstract`. Returns None on failure."""
    akshare_symbol = _to_akshare_symbol(symbol)
    try:
        df = _ak_call("stock_financial_abstract", symbol=akshare_symbol)
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
        (net_income - prior_net_income) / prior_net_income if prior_net_income else None
    )
    gross_margin = 1 - (cost / revenue) if revenue else None
    roe = _profitability_metric(df, _KEY_ROE, latest)
    period, filed = _yyyymmdd_to_period(latest)
    return FilingDigest(
        symbol=_to_qualified_symbol(akshare_symbol),
        fiscal_period=period,
        filed_at_iso=filed,
        revenue_yoy=revenue_yoy,
        net_income_yoy=net_income_yoy,
        gross_margin=gross_margin,
        source_url=_SINA_FINSUMMARY_URL.format(symbol=akshare_symbol),
        roe=roe,
    )
