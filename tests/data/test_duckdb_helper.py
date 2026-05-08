from __future__ import annotations

from pathlib import Path

import pytest

import irc.data.duckdb_helper as duckdb_helper
from irc.data.duckdb_helper import EXPECTED_TABLES, connect, ensure_schema


def test_connect_creates_db_file(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    assert db_path.exists()
    con.close()


def test_ensure_schema_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    actual = {r[0] for r in rows}
    assert EXPECTED_TABLES.issubset(actual)
    con.close()


def test_ensure_schema_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    ensure_schema(con)  # second call must not error
    con.close()


def test_every_table_has_provenance_columns(tmp_path: Path):
    db_path = tmp_path / "test.duckdb"
    con = connect(db_path)
    ensure_schema(con)
    for tbl in EXPECTED_TABLES:
        cols = {
            r[0]
            for r in con.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name='{tbl}'"
            ).fetchall()
        }
        assert {
            "_ingested_at",
            "_source",
            "_raw_ref",
        } <= cols, f"{tbl} missing provenance columns"
    con.close()


def test_ensure_schema_rolls_back_on_ddl_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "broken.duckdb"
    con = connect(db_path)
    broken_ddls = (
        *duckdb_helper._DDL_STATEMENTS[:2],
        "THIS IS NOT VALID SQL",
        *duckdb_helper._DDL_STATEMENTS[2:],
    )
    monkeypatch.setattr(duckdb_helper, "_DDL_STATEMENTS", broken_ddls)
    with pytest.raises(Exception):
        ensure_schema(con)
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    actual = {r[0] for r in rows}
    assert actual.isdisjoint(EXPECTED_TABLES)
    con.close()
