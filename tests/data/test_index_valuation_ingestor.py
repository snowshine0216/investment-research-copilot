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


def test_replace_keys_deletes_prior_rows_on_nonempty_fetch(tmp_path):
    con = _con(tmp_path)
    stale = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-01", 99.0, 9.9, None),  # stale static-PE row
            IndexValuationPoint("2026-05-02", 98.0, 9.8, None),
        ),
    )
    fresh = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    # First write the stale rows (default append).
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: stale, now_iso="2026-05-31T00:00:00+08:00"
    )
    # Now a replace_keys=True run with a non-empty fresh fetch purges the stale rows.
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: fresh,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 1
    rows = con.execute(
        "SELECT CAST(date AS VARCHAR), pe_ttm FROM index_valuation_history "
        "WHERE index_key='csi300' ORDER BY date"
    ).fetchall()
    assert rows == [("2026-05-30", 12.1)]  # ONLY the fresh row survives
    con.close()


def test_replace_keys_preserves_rows_on_none_fetch(tmp_path):
    con = _con(tmp_path)
    existing = IndexValuationHistory(
        index_key="csi300",
        rows=(IndexValuationPoint("2026-05-30", 12.1, 1.31, None),),
    )
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: existing, now_iso="2026-05-31T00:00:00+08:00"
    )
    # A None fetch under replace_keys=True must NOT wipe good cache (transient failure).
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: None,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 0
    assert con.execute(
        "SELECT COUNT(*) FROM index_valuation_history WHERE index_key='csi300'"
    ).fetchone()[0] == 1
    con.close()


def test_replace_keys_skips_key_when_fetch_lacks_pe_ttm(tmp_path):
    """D8: a replace-mode fetch whose rows ALL have pe_ttm=None must NOT wipe or
    overwrite good cached PE rows — skip the key entirely so the cache survives
    a partial-column provider failure (e.g. legulegu returns PB but not 滚动市盈率).
    Both the DELETE and the INSERT OR REPLACE paths must be blocked."""
    con = _con(tmp_path)
    stale = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-01", 13.8, 1.28, None),  # good cached PE
            IndexValuationPoint("2026-05-02", 13.9, 1.29, None),
        ),
    )
    # Seed the stale rows via normal append.
    ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: stale, now_iso="2026-05-31T00:00:00+08:00"
    )
    # A PB-only fetch (all pe_ttm=None) under replace_keys=True must NOT touch cache.
    pb_only = IndexValuationHistory(
        index_key="csi300",
        rows=(
            IndexValuationPoint("2026-05-01", None, 1.31, None),  # pe_ttm=None
            IndexValuationPoint("2026-05-02", None, 1.32, None),  # pe_ttm=None
        ),
    )
    written = ingest_index_valuation_history(
        con, ("csi300",), fetch=lambda k: pb_only,
        now_iso="2026-06-01T00:00:00+08:00", replace_keys=True,
    )
    assert written == 0, "PE-less replace must write 0 rows"
    rows = con.execute(
        "SELECT CAST(date AS VARCHAR), pe_ttm, pb FROM index_valuation_history "
        "WHERE index_key='csi300' ORDER BY date"
    ).fetchall()
    assert len(rows) == 2, "original stale rows must still be present"
    assert rows[0] == ("2026-05-01", 13.8, 1.28), "good pe_ttm must not be overwritten"
    assert rows[1] == ("2026-05-02", 13.9, 1.29), "good pe_ttm must not be overwritten"
    con.close()


def test_default_append_mode_accumulates_across_calls(tmp_path):
    # The sector leg (replace_keys=False) keeps accumulating forward.
    con = _con(tmp_path)
    first = IndexValuationHistory(
        index_key="csi_nonferrous",
        rows=(IndexValuationPoint("2026-05-01", 20.0, None, None),),
    )
    second = IndexValuationHistory(
        index_key="csi_nonferrous",
        rows=(IndexValuationPoint("2026-05-02", 21.0, None, None),),
    )
    ingest_index_valuation_history(
        con, ("csi_nonferrous",), fetch=lambda k: first, now_iso="2026-05-31T00:00:00+08:00"
    )
    ingest_index_valuation_history(
        con, ("csi_nonferrous",), fetch=lambda k: second, now_iso="2026-06-01T00:00:00+08:00"
    )
    # Both dates persist — the first run's row was NOT deleted.
    assert con.execute(
        "SELECT COUNT(*) FROM index_valuation_history WHERE index_key='csi_nonferrous'"
    ).fetchone()[0] == 2
    con.close()
