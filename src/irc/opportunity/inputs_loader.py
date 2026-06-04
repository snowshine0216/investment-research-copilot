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
from irc.fundamentals.provider import CnFundamentalsProvider
from irc.fundamentals.consensus import consensus_upside_pct
from irc.fundamentals.types import BrokerReport
from irc.opportunity.lookthrough import _INDEX_NAME_TO_SLUG, _INDEX_VALUATION_KEYS
from irc.opportunity.types import OpportunityInput
from irc.schemas.valuation import ActiveFundLookthroughConfig


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


_BOND_ASSET_CLASSES_REQUIRING_YIELD: frozenset[str] = frozenset({"cn_bond_fund"})
_CN_10Y_YIELD_SERIES_ID = "cn_10y_yield"
_CPI_YOY_SERIES_ID = "cn_cpi_yoy"  # not ingested in Phase 1; nominal-gap fallback used.

# §3 min-history gate for thin accumulating sector-PE series. Return a non-None
# PE percentile ONLY when the series has >= MIN_PE_POINTS non-null PE
# observations AND spans >= MIN_PE_DAYS calendar days. csi300/csi1000 carry
# thousands of points so the gate is a no-op for broad indices.
MIN_PE_POINTS: int = 120
MIN_PE_DAYS: int = 180


def _cn_bond_yield_percentile(con: duckdb.DuckDBPyConnection) -> float | None:
    """Read the cn_10y_yield series, return the rank-percentile of the latest
    observation. Aligned with `classify_bond_valuation`'s semantics: high
    yield ⇒ high percentile ⇒ bond cheap. Returns None when the series is
    absent or shorter than 2 points.
    """
    df = con.execute(
        "SELECT date, value FROM macro_series WHERE series_id = ? ORDER BY date",
        [_CN_10Y_YIELD_SERIES_ID],
    ).fetchdf()
    if df.empty or len(df) < 2:
        return None
    series = pd.Series(df["value"].to_numpy())
    latest = series.iloc[-1]
    if pd.isna(latest):
        return None
    return float((series <= latest).mean())


def _cn_10y_yield_latest(con: duckdb.DuckDBPyConnection) -> float | None:
    df = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [_CN_10Y_YIELD_SERIES_ID],
    ).fetchdf()
    if df.empty:
        return None
    return _none_if_na(df.iloc[0]["value"])


def _cpi_yoy_latest(con: duckdb.DuckDBPyConnection) -> float | None:
    df = con.execute(
        "SELECT value FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [_CPI_YOY_SERIES_ID],
    ).fetchdf()
    if df.empty:
        return None
    return _none_if_na(df.iloc[0]["value"])


def _real_yield_10y_ratio(con: duckdb.DuckDBPyConnection) -> float | None:
    """R1 ratio units. Default = nominal 10Y CGB yield as a ratio (股债利差).
    If a CN CPI-YoY series is present, switch to the true-real gap. Never reuse
    real_yield_10y_tips (US TIPS, percent)."""
    cn_10y = _cn_10y_yield_latest(con)
    if cn_10y is None:
        return None
    cpi = _cpi_yoy_latest(con)
    if cpi is not None:
        return (cn_10y - cpi) / 100.0
    return cn_10y / 100.0


def _index_valuation_series(
    con: duckdb.DuckDBPyConnection, index_key: str
) -> pd.DataFrame:
    df = con.execute(
        "SELECT date, pe_ttm, pb, dividend_yield FROM index_valuation_history "
        "WHERE index_key = ? ORDER BY date",
        [index_key],
    ).fetchdf()
    return df


def _pe_series_is_mature(pe_series: pd.Series) -> bool:
    """§3 gate: >= MIN_PE_POINTS non-null PE points AND >= MIN_PE_DAYS span."""
    valid = pe_series.dropna()
    if len(valid) < MIN_PE_POINTS:
        return False
    idx = pd.to_datetime(valid.index)
    span_days = (idx.max() - idx.min()).days
    return span_days >= MIN_PE_DAYS


def _index_valuation_metrics(
    con: duckdb.DuckDBPyConnection, tracked_index: str | None,
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Return (pe_ttm, pb, dividend_yield, pe_percentile, pb_percentile) from the
    CACHED index_valuation_history table (R3 — no live fetch). (None,)*5 when the
    index is not a recognised valuation index or has no cached rows.

    The `tracked_index` value may be a display name (e.g. "中证有色金属"); it is
    normalised to a canonical slug via `_INDEX_NAME_TO_SLUG` before membership
    in `_INDEX_VALUATION_KEYS` is tested (§2.1). The PE percentile honours the
    §3 min-history gate AND the latest-null guard.
    """
    norm = (tracked_index or "").strip().lower() or None
    if norm is None:
        return None, None, None, None, None
    slug = _INDEX_NAME_TO_SLUG.get(norm) or norm
    if slug not in _INDEX_VALUATION_KEYS:
        return None, None, None, None, None
    df = _index_valuation_series(con, slug)
    if df.empty:
        return None, None, None, None, None
    latest = df.iloc[-1]
    pe = _none_if_na(latest["pe_ttm"])
    pb = _none_if_na(latest["pb"])
    div = _none_if_na(latest["dividend_yield"])
    pe_series = pd.Series(df["pe_ttm"].to_numpy(), index=pd.to_datetime(df["date"]))
    pb_series = pd.Series(df["pb"].to_numpy(), index=pd.to_datetime(df["date"]))
    pe_pct = (
        self_history_percentile(pe_series)
        if pe is not None and _pe_series_is_mature(pe_series)
        else None
    )
    pb_pct = self_history_percentile(pb_series) if pb is not None else None
    return pe, pb, div, pe_pct, pb_pct


def populate_inputs(
    con: duckdb.DuckDBPyConnection,
    skeleton: OpportunityInput,
    *,
    holding_entry_date: date | None,
    broker_reports: tuple[BrokerReport, ...] = (),
    provider: CnFundamentalsProvider | None = None,
    lookthrough_cfg: ActiveFundLookthroughConfig = ActiveFundLookthroughConfig(),
) -> OpportunityInput:
    """Return a copy of skeleton with evidence fields filled from DuckDB.

    `broker_reports` (default empty) feeds the consensus-upside metric; today
    no wired feed carries target prices, so the metric degrades to None
    (ADR 0009). Index pe/pb/dividend + PE/PB historical percentiles are read
    from the cached `index_valuation_history` table (no live fetch) for
    recognised broad indices and now ground the equity valuation verdict
    (item 001 Phase 1); other vehicles fall back to the NAV percentile.

    The `provider` parameter is retained for API stability and so the
    no-live-fetch test can prove the index path never touches the network;
    it is no longer consumed here (the index fetch moved to the ingest
    stage — R3).
    """
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

    bond_yield_pct = (
        _cn_bond_yield_percentile(con)
        if skeleton.asset_class in _BOND_ASSET_CLASSES_REQUIRING_YIELD
        else None
    )

    latest_close = float(series.iloc[-1]) if not series.empty else None
    upside = consensus_upside_pct(broker_reports, latest_close)
    pe_ttm, pb, dividend_yield, fund_pct, fund_pct_pb = _index_valuation_metrics(
        con, skeleton.tracked_index
    )
    earnings_yield = (
        1.0 / pe_ttm if pe_ttm is not None and pe_ttm > 0 else None
    )
    real_yield = _real_yield_10y_ratio(con)

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
        cn_bond_yield_percentile=bond_yield_pct,
        pe_ttm=pe_ttm,
        pb=pb,
        dividend_yield=dividend_yield,
        consensus_upside_pct=upside,
        valuation_percentile_fundamental=fund_pct,
        valuation_percentile_fundamental_pb=fund_pct_pb,
        earnings_yield=earnings_yield,
        real_yield_10y=real_yield,
    )
