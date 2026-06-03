from __future__ import annotations

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.index_valuation_ingestor import ingest_index_valuation_history
from irc.fundamentals.index_valuation_types import (
    IndexValuationHistory,
    IndexValuationPoint,
)


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "iv.duckdb"))
    ensure_schema(con)
    return con


def test_ingest_writes_one_row_per_date(tmp_path):
    hist = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-28", 11.8, 1.28, None),
            IndexValuationPoint("2026-05-30", 12.1, 1.31, None),
        ),
    )
    con = _con(tmp_path)
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-05-31T00:00:00+08:00"
    )
    assert written == 2
    rows = con.execute(
        "SELECT index_key, CAST(date AS VARCHAR), pe_ttm, pb FROM "
        "index_valuation_history ORDER BY date"
    ).fetchall()
    assert rows[0] == ("csi300", "2026-05-28", 11.8, 1.28)
    assert rows[1] == ("csi300", "2026-05-30", 12.1, 1.31)
    con.close()


def test_ingest_skips_none_history_without_raising(tmp_path):
    con = _con(tmp_path)
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: None, now_iso="2026-05-31T00:00:00+08:00"
    )
    assert written == 0
    assert con.execute("SELECT COUNT(*) FROM index_valuation_history").fetchone()[0] == 0
    con.close()


def test_ingest_is_idempotent_upsert(tmp_path):
    hist = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    con = _con(tmp_path)
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-05-31T00:00:00+08:00"
    )
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: hist, now_iso="2026-06-01T00:00:00+08:00"
    )
    assert con.execute("SELECT COUNT(*) FROM index_valuation_history").fetchone()[0] == 1
    con.close()
