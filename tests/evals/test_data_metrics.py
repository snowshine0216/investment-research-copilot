from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pytest
from irc.data.duckdb_helper import connect, ensure_schema
from evals.data.metrics import (
    freshness_per_source,
    completeness_per_field,
    business_days_elapsed,
)


@pytest.fixture
def db(tmp_path: Path):
    con = connect(tmp_path / "x.duckdb")
    ensure_schema(con)
    today = date.today()
    con.execute(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["VTI", today.isoformat(), 1.0, 1.1, 0.9, 1.05, 1e6,
         datetime.now(timezone(timedelta(hours=8))).isoformat(), "openbb",
         f"openbb:prices:VTI:{today}"]
    )
    yield con
    con.close()


def test_freshness_returns_age_in_days(db):
    out = freshness_per_source(db, source="openbb")
    assert "prices" in out
    assert out["prices"] <= 1


def test_completeness_per_field(db):
    out = completeness_per_field(db, table="prices")
    assert out["close"] == 1.0  # not null
    assert out["instrument_id"] == 1.0


def test_business_days_elapsed_skips_weekend():
    # Fri 2026-06-12 -> Tue 2026-06-16: only Mon+Tue are trading days.
    assert business_days_elapsed(date(2026, 6, 12), date(2026, 6, 16)) == 2


def test_business_days_elapsed_same_day_is_zero():
    assert business_days_elapsed(date(2026, 6, 16), date(2026, 6, 16)) == 0


def test_business_days_elapsed_friday_to_monday_is_one():
    assert business_days_elapsed(date(2026, 6, 12), date(2026, 6, 15)) == 1


def test_business_days_elapsed_saturday_after_friday_is_zero():
    # No new trading day has occurred between Fri close and Sat.
    assert business_days_elapsed(date(2026, 6, 12), date(2026, 6, 13)) == 0


def test_freshness_uses_business_days_over_weekend(tmp_path: Path):
    con = connect(tmp_path / "wk.duckdb")
    ensure_schema(con)
    con.execute(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["VTI", "2026-06-12", 1.0, 1.1, 0.9, 1.05, 1e6,
         "2026-06-12T16:00:00+08:00", "akshare", "akshare:prices:VTI:2026-06-12"],
    )
    try:
        # Evaluated the following Tuesday: 4 calendar days, but only 2 trading days.
        out = freshness_per_source(con, source="akshare", today=date(2026, 6, 16))
        assert out["prices"] == 2
    finally:
        con.close()
