from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _ak_call(fn_name: str, **kwargs: Any) -> Any:
    """Indirection for testability; avoids heavy akshare import at module load."""
    import akshare as ak  # local import
    fn = getattr(ak, fn_name)
    return fn(**kwargs)


def fetch_fund_nav_history(fund_code: str) -> pd.DataFrame:
    """Open-ended fund NAV history. Returns DataFrame with columns: date, nav, nav_acc."""
    df = _ak_call("fund_open_fund_info_em", symbol=fund_code, indicator="单位净值走势")
    if "净值日期" in df.columns:
        df = df.rename(columns={
            "净值日期": "date",
            "单位净值": "nav",
            "累计净值": "nav_acc",
        })
    if "nav_acc" not in df.columns:
        df = df.assign(nav_acc=pd.NA)
    return df[["date", "nav", "nav_acc"]].copy()


def _item_value_dict(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    if {"item", "value"}.issubset(df.columns):
        return {str(r.item): r.value for r in df.itertuples(index=False)}
    if {"项目", "数据"}.issubset(df.columns):
        return dict(zip(df["项目"].astype(str), df["数据"]))
    if len(df) == 1:
        return {str(k): v for k, v in df.iloc[0].to_dict().items()}
    return {}


def _ratios_from_text(value: Any) -> tuple[float, ...]:
    if value is None or pd.isna(value):
        return ()
    text = str(value).strip().replace("％", "%")
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if matches:
        return tuple(float(match) / 100 for match in matches)
    try:
        return (float(text),)
    except ValueError:
        return ()


def _expense_ratio_from_fee_table(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    total = 0.0
    found = False
    for row in df.itertuples(index=False, name=None):
        row_text = " ".join(str(v) for v in row if not pd.isna(v))
        if not any(label in row_text for label in ("管理费", "托管费", "销售服务费")):
            continue
        ratios = _ratios_from_text(row_text)
        if ratios:
            total += sum(ratios)
            found = True
    return total if found else None


def fetch_fund_metadata(fund_code: str) -> dict[str, Any]:
    """Single-row metadata dict: fund_code, name_cn, fund_type, aum_text, inception_date, expense_ratio."""
    try:
        basic = _item_value_dict(_ak_call("fund_individual_basic_info_xq", symbol=fund_code))
    except Exception:
        # XueQiu API requires auth cookies; fall back to East Money
        basic = _item_value_dict(_ak_call("fund_individual_basic_info_em", symbol=fund_code))
    if not basic or str(basic.get("基金代码") or basic.get("fund_code") or "") != fund_code:
        raise ValueError(f"fund {fund_code!r} not found in AKShare basic info")
    fees = _ak_call("fund_fee_em", symbol=fund_code, indicator="运作费用")
    return {
        "fund_code": str(basic.get("基金代码") or basic.get("fund_code") or fund_code),
        "name_cn": str(basic.get("基金名称") or basic.get("基金简称") or basic.get("name_cn") or ""),
        "fund_type": str(basic.get("基金类型") or basic.get("fund_type") or ""),
        "aum_text": str(basic.get("最新规模") or basic.get("基金规模") or basic.get("资产规模") or basic.get("aum_text") or ""),
        "inception_date": str(basic.get("成立时间") or basic.get("成立日期") or "") or None,
        "expense_ratio": _expense_ratio_from_fee_table(fees),
        "manager_tenure_years": basic.get("manager_tenure_years") or basic.get("基金经理任职年限"),
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
