from __future__ import annotations
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pytest
from irc.data.duckdb_helper import connect, ensure_schema
from evals.data.metrics import freshness_per_source, completeness_per_field


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
