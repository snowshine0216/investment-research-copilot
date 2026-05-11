from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import duckdb
import pandas as pd


def derive_risk_metrics(values: pd.Series) -> dict[str, float]:
    series = values.dropna().astype(float)
    if len(series) < 2:
        return {"drawdown_3y": math.nan, "vol_1y": math.nan, "downside_capture": math.nan}
    running_max = series.cummax()
    drawdowns = (running_max - series) / running_max
    returns = series.pct_change().dropna()
    downside = returns[returns < 0]
    return {
        "drawdown_3y": float(drawdowns.max()),
        "vol_1y": float(returns.std(ddof=0) * math.sqrt(252)) if not returns.empty else math.nan,
        "downside_capture": float(abs(downside.mean()) / abs(returns.mean())) if not downside.empty and returns.mean() != 0 else 0.0,
    }


def load_scoring_metrics(con: duckdb.DuckDBPyConnection, instrument_ids: Iterable[str]) -> pd.DataFrame:
    ids = tuple(str(instrument_id) for instrument_id in instrument_ids)
    if not ids:
        return _empty_metrics_frame()
    rows = [_metrics_for_instrument(con, instrument_id) for instrument_id in ids]
    return pd.DataFrame(rows)


def _metrics_for_instrument(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    base = _instrument_base(con, instrument_id)
    latest_fund = _latest_fund_metrics(con, instrument_id)
    prices = _price_or_nav_series(con, instrument_id)
    risk = derive_risk_metrics(prices) if not prices.empty else {}
    concentration = _latest_holdings_concentration(con, instrument_id)
    # aum_stability_pct requires a multi-period AUM history we do not yet ingest.
    # Honest "missing" (NaN) is required so Phase 2 completeness gates fire correctly
    # on instruments lacking AUM-stability evidence. Do not fake a 0.0 stability value.
    return {
        "instrument_id": instrument_id,
        "expense_ratio": base.get("expense_ratio"),
        "drawdown_3y": _coalesce(latest_fund.get("drawdown_3y"), risk.get("drawdown_3y")),
        "vol_1y": _coalesce(latest_fund.get("vol_1y"), risk.get("vol_1y")),
        "downside_capture": _coalesce(latest_fund.get("downside_capture"), risk.get("downside_capture")),
        "aum_stability_pct": math.nan,
        "manager_tenure_years": base.get("manager_tenure_years"),
        "holdings_concentration_top10": concentration,
    }


def _coalesce(*values: Any) -> Any:
    """Return the first non-None, non-NaN value, else NaN.

    `dict.get(key, fallback)` only returns `fallback` when the key is absent;
    if the key exists but the value is None or NaN, the fallback is skipped.
    This helper makes fund_metrics → derived-from-prices fallback honest.
    """
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        return value
    return math.nan


def _instrument_base(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    result = con.execute(
        "SELECT expense_ratio, aum, manager_tenure_years FROM instruments WHERE instrument_id = ?",
        [instrument_id],
    ).fetchone()
    if result is None:
        return {}
    return {"expense_ratio": result[0], "aum": result[1], "manager_tenure_years": result[2]}


def _latest_fund_metrics(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict[str, Any]:
    result = con.execute(
        """
        SELECT drawdown_3y, vol_1y, downside_capture
        FROM fund_metrics
        WHERE instrument_id = ?
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        [instrument_id],
    ).fetchone()
    if result is None:
        return {}
    return {"drawdown_3y": result[0], "vol_1y": result[1], "downside_capture": result[2]}


def _price_or_nav_series(con: duckdb.DuckDBPyConnection, instrument_id: str) -> pd.Series:
    prices = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if not prices.empty:
        return pd.Series(prices["close"].to_numpy(), index=pd.to_datetime(prices["date"]))
    nav = con.execute(
        "SELECT date, nav FROM nav_history WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if nav.empty:
        return pd.Series(dtype=float)
    return pd.Series(nav["nav"].to_numpy(), index=pd.to_datetime(nav["date"]))


def _latest_holdings_concentration(con: duckdb.DuckDBPyConnection, instrument_id: str) -> float:
    result = con.execute(
        """
        SELECT SUM(weight_pct) / 100.0
        FROM (
            SELECT weight_pct
            FROM fund_holdings
            WHERE instrument_id = ?
              AND report_date = (SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?)
            ORDER BY weight_pct DESC
            LIMIT 10
        )
        """,
        [instrument_id, instrument_id],
    ).fetchone()
    if result is None or result[0] is None:
        return math.nan
    return float(result[0])


def _empty_metrics_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "instrument_id",
        "expense_ratio",
        "drawdown_3y",
        "vol_1y",
        "downside_capture",
        "aum_stability_pct",
        "manager_tenure_years",
        "holdings_concentration_top10",
    ])
