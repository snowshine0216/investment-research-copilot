"""Tests for `read_live_decision_inputs` after extraction from decision_cmd.

I/O wrapper: pure read over `data/local.duckdb`. Graceful degrade on
DB-missing / connect-fail / query-fail returns ({}, {}).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from irc.decision.live_inputs import read_live_decision_inputs


def test_read_live_decision_inputs_returns_empty_when_db_missing(
    tmp_path: Path,
) -> None:
    """When `data/local.duckdb` does not exist the helper returns ({}, {})
    so the renderer can gracefully show 'unknown' rather than crashing."""
    # tmp_path/data/local.duckdb intentionally not created.
    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})
    assert macro == {}
    assert returns == {}


def test_read_live_decision_inputs_reads_macro_and_returns(tmp_path: Path) -> None:
    """Happy path: macro_series row + 8 nav_history rows → populated dicts."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "local.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE macro_series ("
        "  series_id VARCHAR, date DATE, value DOUBLE"
        ")"
    )
    con.execute(
        "INSERT INTO macro_series VALUES "
        "('vix', '2026-05-25', 16.76), "
        "('vix', '2026-05-20', 17.50)"  # older row should be filtered out
    )
    con.execute(
        "CREATE TABLE nav_history ("
        "  instrument_id VARCHAR, date DATE, nav DOUBLE"
        ")"
    )
    # 8 NAV points in ascending date order — latest date gets the highest NAV.
    # ORDER BY date DESC means iloc[0]=latest=1.10, iloc[-1]=oldest=1.00.
    # return = 1.10 / 1.00 - 1 = 0.10
    for i, nav in enumerate([1.00, 1.01, 1.02, 1.03, 1.04, 1.06, 1.08, 1.10]):
        con.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?)",
            ["510300", f"2026-05-{18 + i:02d}", nav],
        )
    con.close()

    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})

    assert macro == {"vix": 16.76}
    # latest (1.10) / oldest (1.00) - 1 = 0.10
    assert returns["510300"] == pytest.approx(0.10)


def test_read_live_decision_inputs_logs_on_query_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """P0-1 fix: catastrophic query failures emit a WARNING to stderr, not
    a silent empty dict. Uses an empty DB (no schema) so the macro_series
    query raises a CatalogException mid-run."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "local.duckdb"
    # Create an empty DuckDB file — no tables — so the macro_series query fails.
    con = duckdb.connect(str(db_path))
    con.close()

    macro, returns = read_live_decision_inputs(tmp_path, instrument_ids={"510300"})

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "live_inputs query failed" in captured.err
    assert macro == {}
    assert returns == {}


def test_read_live_decision_inputs_skips_instruments_with_too_few_navs(
    tmp_path: Path,
) -> None:
    """Fewer than 5 NAV rows → instrument absent from returns dict.
    Renderer shows 'missing' rather than a spurious value."""
    db_dir = tmp_path / "data"
    db_dir.mkdir()
    db_path = db_dir / "local.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE macro_series (series_id VARCHAR, date DATE, value DOUBLE)"
    )
    con.execute(
        "CREATE TABLE nav_history (instrument_id VARCHAR, date DATE, nav DOUBLE)"
    )
    # Only 4 NAV rows — below the 5-row threshold.
    for i, nav in enumerate([1.10, 1.09, 1.08, 1.07]):
        con.execute(
            "INSERT INTO nav_history VALUES (?, ?, ?)",
            ["510300", f"2026-05-{18 + i:02d}", nav],
        )
    con.close()

    macro, returns = read_live_decision_inputs(tmp_path, {"510300"})
    assert macro == {}
    assert returns == {}
