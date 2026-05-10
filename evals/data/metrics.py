from __future__ import annotations
from datetime import date
import duckdb


def freshness_per_source(con: duckdb.DuckDBPyConnection, source: str) -> dict[str, int]:
    """For each table, days since most recent record from given source."""
    out: dict[str, int] = {}
    for tbl in ("prices", "nav_history", "macro_series"):
        row = con.execute(
            f"SELECT MAX(date) FROM {tbl} WHERE _source = ?",
            [source],
        ).fetchone()
        latest = row[0] if row else None
        if latest is None:
            continue
        age = (date.today() - latest).days
        out[tbl] = age
    return out


def completeness_per_field(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, float]:
    """Fraction of non-null values per column."""
    cols = con.execute(
        f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'"
    ).fetchall()
    result: dict[str, float] = {}
    total = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if total == 0:
        return {c[0]: 1.0 for c in cols}
    for (col,) in cols:
        non_null = con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        result[col] = non_null / total
    return result
