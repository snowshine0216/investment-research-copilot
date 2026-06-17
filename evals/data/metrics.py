from __future__ import annotations
from datetime import date, timedelta
import duckdb


def business_days_elapsed(latest: date, today: date) -> int:
    """Trading-day staleness: count Mon–Fri days strictly after ``latest`` up to
    and including ``today``. Market data is not published on weekends, so a
    Friday close evaluated the following Tuesday is 2 trading days old, not 4
    calendar days — counting calendar days false-flags every Mon/Tue run.
    (Public holidays are not modelled; this is intentionally conservative —
    it never under-counts staleness.)"""
    if today <= latest:
        return 0
    days = 0
    cursor = latest + timedelta(days=1)
    while cursor <= today:
        if cursor.weekday() < 5:  # Mon=0 .. Fri=4
            days += 1
        cursor += timedelta(days=1)
    return days


def freshness_per_source(
    con: duckdb.DuckDBPyConnection, source: str, *, today: date | None = None,
) -> dict[str, int]:
    """For each table, trading days since the most recent record from ``source``.

    ``today`` is injectable for deterministic tests; defaults to ``date.today()``."""
    anchor = today or date.today()
    out: dict[str, int] = {}
    for tbl in ("prices", "nav_history", "macro_series"):
        row = con.execute(
            f"SELECT MAX(date) FROM {tbl} WHERE _source = ?",
            [source],
        ).fetchone()
        latest = row[0] if row else None
        if latest is None:
            continue
        out[tbl] = business_days_elapsed(latest, anchor)
    return out


_ALLOWED_TABLES = frozenset({"prices", "nav_history", "macro_series", "raw_ref"})


def completeness_per_field(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, float]:
    """Fraction of non-null values per column."""
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table {table!r} not in allowlist {_ALLOWED_TABLES}")
    cols = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=?",
        [table],
    ).fetchall()
    result: dict[str, float] = {}
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 — table is allowlisted
    if total == 0:
        return {c[0]: 1.0 for c in cols}
    for (col,) in cols:
        safe_col = '"' + col.replace('"', '""') + '"'
        non_null = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {safe_col} IS NOT NULL"  # noqa: S608 — col is quoted
        ).fetchone()[0]
        result[col] = non_null / total
    return result
