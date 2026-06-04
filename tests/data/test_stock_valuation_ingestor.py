from __future__ import annotations

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.stock_valuation_ingestor import (
    ingest_stock_valuation_history,
    is_stock_valuation_stale,
)
from irc.fundamentals.stock_valuation_types import (
    StockValuationHistory,
    StockValuationPoint,
)


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "sv.duckdb"))
    ensure_schema(con)
    return con


def _hist(code, source="eastmoney"):
    return StockValuationHistory(
        stock_code=code,
        rows=(
            StockValuationPoint("2026-05-28", 18.0, 2.0, None),
            StockValuationPoint("2026-05-30", 18.2, 2.1, None),
        ),
    ), source


def test_ingest_writes_one_row_per_date_with_source(tmp_path) -> None:
    con = _con(tmp_path)
    written = ingest_stock_valuation_history(
        con, ("600519",),
        fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    assert written == 2
    rows = con.execute(
        "SELECT stock_code, CAST(date AS VARCHAR), pe_ttm, pb, _source "
        "FROM stock_valuation_history ORDER BY date"
    ).fetchall()
    assert rows[0] == ("600519", "2026-05-28", 18.0, 2.0, "eastmoney")
    assert rows[1][4] == "eastmoney"
    con.close()


def test_ingest_records_per_row_source_from_fetch(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("000001",),
        fetch=lambda code: _hist(code, source="tushare"),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    src = con.execute(
        "SELECT DISTINCT _source FROM stock_valuation_history WHERE stock_code='000001'"
    ).fetchone()[0]
    assert src == "tushare"
    con.close()


def test_ingest_skips_none_history_without_raising(tmp_path) -> None:
    con = _con(tmp_path)
    written = ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: None,
        now_iso="2026-05-31T00:00:00+08:00",
    )
    assert written == 0
    con.close()


def test_ingest_is_idempotent_upsert(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-06-01T00:00:00+08:00",
    )
    n = con.execute(
        "SELECT COUNT(*) FROM stock_valuation_history WHERE stock_code='600519'"
    ).fetchone()[0]
    assert n == 2
    con.close()


def test_is_stale_true_when_no_rows(tmp_path) -> None:
    con = _con(tmp_path)
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-05-31", threshold_days=30
    ) is True
    con.close()


def test_is_stale_false_when_fresh(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    # latest date 2026-05-30; today 2026-05-31 → age 1 day < 30 → fresh.
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-05-31", threshold_days=30
    ) is False
    con.close()


def test_is_stale_true_when_older_than_threshold(tmp_path) -> None:
    con = _con(tmp_path)
    ingest_stock_valuation_history(
        con, ("600519",), fetch=lambda code: _hist(code),
        now_iso="2026-05-31T00:00:00+08:00",
    )
    # latest 2026-05-30; today 2026-08-30 → age ~92 days > 30 → stale.
    assert is_stock_valuation_stale(
        con, "600519", today_iso="2026-08-30", threshold_days=30
    ) is True
    con.close()
