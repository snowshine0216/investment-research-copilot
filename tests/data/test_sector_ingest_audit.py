from __future__ import annotations

from datetime import date

import duckdb

from irc.data.duckdb_helper import ensure_schema
from irc.data.index_valuation_ingestor import audit_sector_ingest


def _con(tmp_path):
    con = duckdb.connect(str(tmp_path / "audit.duckdb"))
    ensure_schema(con)
    return con


def _seed(con, index_key, n, *, base=date(2025, 1, 1), pe=12.0):
    rows = [
        (index_key, date.fromordinal(base.toordinal() + i), pe, None, None)
        for i in range(n)
    ]
    con.executemany(
        "INSERT INTO index_valuation_history VALUES "
        "(?,?,?,?,?, TIMESTAMP '2026-05-15', 'test', 'test:iv')",
        rows,
    )


def test_audit_covers_all_17_slugs_even_when_empty(tmp_path):
    con = _con(tmp_path)
    rows = audit_sector_ingest(con)
    assert len(rows) == 17  # every sector slug reported, even with 0 rows
    by_slug = {r.slug: r for r in rows}
    r = by_slug["csi_robotics"]
    assert r.row_count == 0
    assert r.has_numeric_pe is False
    assert r.latest_date is None
    assert r.mature is False
    con.close()


def test_audit_reports_accumulating_not_mature(tmp_path):
    con = _con(tmp_path)
    _seed(con, "csi_robotics", 20)  # < 120 points, < 180 day span
    rows = {r.slug: r for r in audit_sector_ingest(con)}
    r = rows["csi_robotics"]
    assert r.row_count == 20
    assert r.has_numeric_pe is True
    assert r.points == 20
    assert r.mature is False  # 20 < MIN_PE_POINTS (120) -> B1 expected state


def test_audit_reports_mature_when_thresholds_cleared(tmp_path):
    con = _con(tmp_path)
    _seed(con, "csi_robotics", 200)  # 200 points, 199-day span
    rows = {r.slug: r for r in audit_sector_ingest(con)}
    r = rows["csi_robotics"]
    assert r.points >= 120
    assert r.span_days >= 180
    assert r.mature is True
