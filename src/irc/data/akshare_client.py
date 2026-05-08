from __future__ import annotations

from typing import Any

import pandas as pd


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids heavy akshare import at module load."""
    import akshare as ak  # local import
    fn = getattr(ak, fn_name)
    return fn(**kwargs)


def fetch_fund_nav_history(fund_code: str) -> pd.DataFrame:
    """Open-ended fund NAV history. Returns DataFrame with columns: date, nav, nav_acc."""
    df = _ak_call("fund_open_fund_info_em", fund=fund_code, indicator="单位净值走势")
    if "净值日期" in df.columns:
        df = df.rename(columns={
            "净值日期": "date",
            "单位净值": "nav",
            "累计净值": "nav_acc",
        })
    return df[["date", "nav", "nav_acc"]].copy()


def fetch_fund_metadata(fund_code: str) -> dict[str, Any]:
    """Single-row metadata dict: fund_code, name_cn, fund_type, aum_text, inception_date, expense_ratio."""
    df = _ak_call("fund_name_em")
    if isinstance(df, pd.DataFrame):
        mask = df.get("基金代码", df.get("fund_code", pd.Series(dtype=str))) == fund_code
        rows = df[mask]
        row = rows.iloc[0].to_dict() if not rows.empty else df.iloc[0].to_dict()
    else:
        row = dict(df)
    return {
        "fund_code": str(row.get("基金代码") or row.get("fund_code") or fund_code),
        "name_cn": str(row.get("基金简称") or row.get("name_cn") or ""),
        "fund_type": str(row.get("基金类型") or row.get("fund_type") or ""),
        "aum_text": str(row.get("基金规模") or row.get("aum_text") or ""),
        "inception_date": str(row.get("成立日期") or row.get("inception_date") or "") or None,
        "expense_ratio": float(row.get("费率") or row.get("expense_ratio") or 0.0),
    }


def fetch_etf_metadata(symbol: str) -> dict[str, Any]:
    """On-exchange ETF metadata; symbol is 6-digit code (e.g. '510300')."""
    df = _ak_call("fund_etf_category_sina", symbol="ETF基金")
    if isinstance(df, pd.DataFrame):
        code_col = "代码" if "代码" in df.columns else "symbol"
        rows = df[df[code_col].astype(str).str.contains(symbol, regex=False)]
        row = rows.iloc[0].to_dict() if not rows.empty else {}
    else:
        row = dict(df)
    return {
        "ticker": symbol,
        "name_cn": str(row.get("名称") or row.get("name") or ""),
    }
