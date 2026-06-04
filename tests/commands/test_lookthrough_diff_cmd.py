from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from irc.commands.lookthrough_diff_cmd import run_lookthrough_diff
from irc.data.duckdb_helper import ensure_schema


def _seed(db_path):
    con = duckdb.connect(str(db_path))
    ensure_schema(con)
    con.execute(
        "INSERT INTO instruments VALUES "
        "('AF1','AF1','cn_off_exchange','主动基金',NULL,'cn_equity_fund','cny',"
        " DATE '2020-01-01', 0.015, 1.0e9, NULL, 3.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    con.execute(
        "INSERT INTO fund_holdings VALUES "
        "('AF1', DATE '2026-03-31', '600519', '贵州茅台', 60.0, "
        " TIMESTAMP '2026-05-15', 'test', 'r')"
    )
    base = date(2025, 1, 1)
    rows = [("600519", date.fromordinal(base.toordinal() + 2 * i), 18.0 + i * 0.01, 2.0, None,
             "2026-05-15 00:00:00", "eastmoney", "r") for i in range(200)]
    con.executemany("INSERT INTO stock_valuation_history VALUES (?,?,?,?,?,?,?,?)", rows)
    con.close()


def test_run_writes_diff_report_artifact(tmp_path) -> None:
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed(db)
    out = tmp_path / "out"
    rc = run_lookthrough_diff(str(tmp_path), output_dir=str(out))
    assert rc == 0
    artifact = out / "lookthrough_diff_report.md"
    assert artifact.exists()
    text = artifact.read_text(encoding="utf-8")
    assert "AF1" in text
    assert "0.40" in text and "0.50" in text and "0.60" in text


def test_run_computes_regardless_of_flag(tmp_path) -> None:
    # The command never reads active_fund_lookthrough.enabled — it always
    # computes (spec §8). Smoke: it produces a non-empty report with the data.
    db = tmp_path / "data" / "local.duckdb"
    db.parent.mkdir(parents=True)
    _seed(db)
    out = tmp_path / "out"
    rc = run_lookthrough_diff(str(tmp_path), output_dir=str(out), coverage_floor=0.50)
    assert rc == 0
    assert (out / "lookthrough_diff_report.md").read_text(encoding="utf-8").strip()
