from __future__ import annotations

from pathlib import Path

from irc.data.duckdb_helper import connect, ensure_schema
from irc.data.raw_ref import RawRef, build_ref_id, is_reachable, ref_index_from_duckdb


def test_build_ref_id_is_stable() -> None:
    a = build_ref_id("openbb", "prices", "510300", "2026-05-07")
    b = build_ref_id("openbb", "prices", "510300", "2026-05-07")
    assert a == b
    assert a == "openbb:prices:510300:2026-05-07"


def test_ref_index_collects_all_raw_refs(tmp_path: Path) -> None:
    db = tmp_path / "x.duckdb"
    con = connect(db)
    ensure_schema(con)
    con.execute(
        """
        INSERT INTO prices
            (instrument_id, date, open, high, low, close, volume,
             _ingested_at, _source, _raw_ref)
        VALUES
            ('510300', '2026-05-06', 4.20, 4.25, 4.18, 4.22, 1e8,
             '2026-05-07T10:00:00+08:00', 'openbb', 'openbb:prices:510300:2026-05-06')
        """
    )
    con.execute(
        """
        INSERT INTO macro_series
            (series_id, date, value, _ingested_at, _source, _raw_ref)
        VALUES
            ('CPI_YOY', '2026-04-30', 0.21,
             '2026-05-07T10:00:00+08:00', 'akshare', 'akshare:macro_series:CPI_YOY:2026-04-30')
        """
    )
    idx = ref_index_from_duckdb(con)
    con.close()
    assert "openbb:prices:510300:2026-05-06" in idx
    assert "akshare:macro_series:CPI_YOY:2026-04-30" in idx


def test_is_reachable_in_index() -> None:
    idx = {"openbb:prices:510300:2026-05-06"}
    assert is_reachable(
        RawRef(
            source="openbb",
            retrieved_at="x",
            topic="prices",
            raw_artifact_path="openbb:prices:510300:2026-05-06",
        ),
        idx,
    )
    assert not is_reachable(
        RawRef(
            source="openbb",
            retrieved_at="x",
            topic="prices",
            raw_artifact_path="openbb:prices:000000:2026-05-06",
        ),
        idx,
    )