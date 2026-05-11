from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from irc.data.duckdb_helper import connect, ensure_schema
from irc.scoring.metrics_loader import derive_risk_metrics, load_scoring_metrics


def test_derive_risk_metrics_from_price_series() -> None:
    series = pd.Series(
        [100.0, 110.0, 105.0, 120.0, 90.0, 95.0],
        index=pd.date_range("2026-01-01", periods=6),
    )

    metrics = derive_risk_metrics(series)

    assert metrics["drawdown_3y"] == 0.25
    assert metrics["vol_1y"] > 0.0
    assert metrics["downside_capture"] >= 0.0


def test_load_scoring_metrics_combines_instruments_prices_and_holdings(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    ingested_at = "2026-05-11 00:00:00"
    con.execute(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["050025", "050025", "cn_off_exchange", "博时标普500", None, "us_etf", "cny", date(2012, 1, 1), 0.006, 1_000_000_000.0, "S&P 500", 8.0, ingested_at, "test", "ref_inst"],
    )
    start = date(2026, 1, 1)
    for offset, close in enumerate([100.0, 102.0, 101.0, 104.0, 103.0, 105.0]):
        con.execute(
            "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["050025", start + timedelta(days=offset), None, None, None, close, 1000.0, ingested_at, "test", f"ref_price_{offset}"],
        )
    for rank, weight in enumerate([20.0, 15.0, 10.0], start=1):
        con.execute(
            "INSERT INTO fund_holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["050025", date(2026, 3, 31), f"H{rank}", f"Holding {rank}", weight, ingested_at, "test", f"ref_holding_{rank}"],
        )

    metrics = load_scoring_metrics(con, ["050025"])

    assert list(metrics["instrument_id"]) == ["050025"]
    row = metrics.iloc[0].to_dict()
    assert row["expense_ratio"] == 0.006
    assert row["manager_tenure_years"] == 8.0
    assert row["holdings_concentration_top10"] == 0.45
    assert row["drawdown_3y"] >= 0.0
    # aum_stability_pct must stay NaN until a real AUM-history derivation lands.
    # Phase 2 honest-missing-data goal forbids faking a 0.0 stability value.
    assert pd.isna(row["aum_stability_pct"])
    con.close()


def test_derive_risk_metrics_short_series_returns_all_nan() -> None:
    series = pd.Series([100.0], index=pd.date_range("2026-01-01", periods=1))

    metrics = derive_risk_metrics(series)

    assert math.isnan(metrics["drawdown_3y"])
    assert math.isnan(metrics["vol_1y"])
    assert math.isnan(metrics["downside_capture"])


def test_derive_risk_metrics_no_downside_returns_zero_capture() -> None:
    # All prices monotonically increasing → no negative returns → downside_capture=0.0
    series = pd.Series([100.0, 105.0, 110.0, 115.0, 120.0], index=pd.date_range("2026-01-01", periods=5))

    metrics = derive_risk_metrics(series)

    assert metrics["downside_capture"] == pytest.approx(0.0)


def test_load_scoring_metrics_empty_ids_returns_empty_dataframe(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)

    df = load_scoring_metrics(con, [])

    assert df.empty
    assert "instrument_id" in df.columns
    con.close()


def test_load_scoring_metrics_unknown_instrument_yields_nan_fields(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)

    df = load_scoring_metrics(con, ["NOT_IN_DB"])

    assert len(df) == 1
    row = df.iloc[0].to_dict()
    assert row["instrument_id"] == "NOT_IN_DB"
    assert row["expense_ratio"] is None
    assert math.isnan(row["drawdown_3y"])
    con.close()


def test_load_scoring_metrics_no_holdings_returns_nan_concentration(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    ingested_at = "2026-05-11 00:00:00"
    con.execute(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["NOHOLDS", "NOHOLDS", "cn_off_exchange", "TestFund", None, "us_etf", "cny", date(2020, 1, 1), 0.005, 500_000_000.0, "TestIdx", 5.0, ingested_at, "test", "ref_noholds"],
    )

    df = load_scoring_metrics(con, ["NOHOLDS"])
    row = df.iloc[0].to_dict()

    assert math.isnan(row["holdings_concentration_top10"])
    con.close()


def test_load_scoring_metrics_uses_nav_history_when_prices_absent(tmp_path: Path) -> None:
    con = connect(tmp_path / "local.duckdb")
    ensure_schema(con)
    ingested_at = "2026-05-11 00:00:00"
    con.execute(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["NAVONLY", "NAVONLY", "cn_off_exchange", "NavFund", None, "cn_off_exchange", "cny", date(2020, 1, 1), 0.008, 200_000_000.0, None, 3.0, ingested_at, "test", "ref_navonly"],
    )
    start = date(2026, 1, 1)
    for offset, nav in enumerate([1.0, 1.05, 1.03, 1.08, 1.06]):
        con.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["NAVONLY", start + timedelta(days=offset), float(1.0 + offset * 0.02), None, ingested_at, "test", f"ref_nav_{offset}"],
        )

    df = load_scoring_metrics(con, ["NAVONLY"])

    assert len(df) == 1
    row = df.iloc[0].to_dict()
    assert row["instrument_id"] == "NAVONLY"
    assert not math.isnan(row["drawdown_3y"])
    con.close()
