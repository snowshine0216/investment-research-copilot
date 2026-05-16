from __future__ import annotations

from dataclasses import replace
from datetime import date

import duckdb
import pandas as pd

from irc.opportunity.returns import (
    drawdown_since_entry,
    rolling_returns,
    self_history_percentile,
)
from irc.opportunity.types import OpportunityInput


def _instrument_meta(con: duckdb.DuckDBPyConnection, instrument_id: str) -> dict:
    df = con.execute(
        "SELECT expense_ratio, aum, manager_tenure_years FROM instruments WHERE instrument_id = ?",
        [instrument_id],
    ).fetchdf()
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "expense_ratio": _none_if_na(row["expense_ratio"]),
        "aum_cny": _none_if_na(row["aum"]),
        "manager_tenure_years": _none_if_na(row["manager_tenure_years"]),
    }


def _tracking_error(con: duckdb.DuckDBPyConnection, instrument_id: str) -> float | None:
    df = con.execute(
        "SELECT tracking_error FROM fund_metrics "
        "WHERE instrument_id = ? ORDER BY as_of_date DESC LIMIT 1",
        [instrument_id],
    ).fetchdf()
    if df.empty:
        return None
    return _none_if_na(df.iloc[0]["tracking_error"])


def _price_series(con: duckdb.DuckDBPyConnection, instrument_id: str) -> pd.Series:
    df = con.execute(
        "SELECT date, close FROM prices WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if not df.empty:
        return pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["date"]))
    df = con.execute(
        "SELECT date, nav FROM nav_history WHERE instrument_id = ? ORDER BY date",
        [instrument_id],
    ).fetchdf()
    if df.empty:
        return pd.Series(dtype=float)
    return pd.Series(df["nav"].to_numpy(), index=pd.to_datetime(df["date"]))


def _none_if_na(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
) -> OpportunityInput:
    """Return a copy of skeleton with evidence fields filled from DuckDB."""
    meta = _instrument_meta(con, skeleton.instrument_id)
    tracking_err = _tracking_error(con, skeleton.instrument_id)
    series = _price_series(con, skeleton.instrument_id)

    if series.empty:
        returns = {"ret_1m": None, "ret_3m": None, "ret_6m": None, "ret_12m": None}
        percentile = None
        dd = None
    else:
        as_of = series.index[-1]
        returns = rolling_returns(series, as_of=as_of)
        percentile = self_history_percentile(series)
        dd = (
            drawdown_since_entry(series, entry_date=pd.Timestamp(holding_entry_date))
            if holding_entry_date is not None
            else None
        )

    return replace(
        skeleton,
        expense_ratio=meta.get("expense_ratio"),
        aum_cny=meta.get("aum_cny"),
        manager_tenure_years=meta.get("manager_tenure_years"),
        tracking_error=tracking_err,
        ret_1m=returns["ret_1m"],
        ret_3m=returns["ret_3m"],
        ret_6m=returns["ret_6m"],
        ret_12m=returns["ret_12m"],
        valuation_percentile_self=percentile,
        drawdown_since_entry=dd,
    )
