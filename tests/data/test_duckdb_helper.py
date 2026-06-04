from __future__ import annotations

from pathlib import Path

import duckdb
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


def test_fund_holdings_ddl_is_byte_equal_to_locked_baseline() -> None:
    """AC1 — item 010 must NOT mutate the fund_holdings DDL. The locked
    baseline below is the captured pre-item-010 string. If this test fails,
    either: (a) the schema was intentionally changed (update the baseline
    and the spec), or (b) the change was accidental — revert it."""
    from irc.data.duckdb_helper import _DDL_STATEMENTS, _PROVENANCE_COLS
    expected = (
        f"""CREATE TABLE IF NOT EXISTS fund_holdings (
        instrument_id     VARCHAR NOT NULL,
        report_date       DATE    NOT NULL,
        holding_ticker    VARCHAR NOT NULL,
        holding_name      VARCHAR,
        weight_pct        DOUBLE  NOT NULL,
        {_PROVENANCE_COLS},
        PRIMARY KEY (instrument_id, report_date, holding_ticker)
    )"""
    )
    matches = [
        s for s in _DDL_STATEMENTS
        if "CREATE TABLE IF NOT EXISTS fund_holdings" in s
    ]
    assert len(matches) == 1, "exactly one fund_holdings DDL expected"
    assert matches[0] == expected, (
        "fund_holdings DDL drift detected — locked by AC1.\n"
        f"expected:\n{expected!r}\nactual:\n{matches[0]!r}"
    )


def test_fund_holdings_remains_in_expected_tables() -> None:
    """AC1 corollary — fund_holdings is still listed in EXPECTED_TABLES."""
    from irc.data.duckdb_helper import EXPECTED_TABLES
    assert "fund_holdings" in EXPECTED_TABLES


def test_index_valuation_history_in_expected_tables() -> None:
    assert "index_valuation_history" in EXPECTED_TABLES


def test_ensure_schema_creates_index_valuation_history(tmp_path) -> None:
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    ensure_schema(con)
    cols = {
        r[1]
        for r in con.execute("PRAGMA table_info('index_valuation_history')").fetchall()
    }
    assert {"index_key", "date", "pe_ttm", "pb", "dividend_yield"} <= cols
    # Idempotent: a second call must not raise.
    ensure_schema(con)
    con.close()


def test_stock_valuation_history_in_expected_tables() -> None:
    from irc.data.duckdb_helper import EXPECTED_TABLES
    assert "stock_valuation_history" in EXPECTED_TABLES


def test_ensure_schema_creates_stock_valuation_history(tmp_path) -> None:
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "sv.duckdb")
    ensure_schema(con)
    cols = {
        r[1] for r in con.execute(
            "PRAGMA table_info('stock_valuation_history')"
        ).fetchall()
    }
    assert {
        "stock_code", "date", "pe_ttm", "pb", "dividend_yield",
        "_ingested_at", "_source", "_raw_ref",
    } <= cols
    con.close()


def test_stock_valuation_history_primary_key_is_stock_code_date(tmp_path) -> None:
    from irc.data.duckdb_helper import connect, ensure_schema
    con = connect(tmp_path / "sv.duckdb")
    ensure_schema(con)
    pk = [
        r[1] for r in con.execute(
            "PRAGMA table_info('stock_valuation_history')"
        ).fetchall() if r[5]  # r[5] = pk flag
    ]
    assert pk == ["stock_code", "date"]
    con.close()
