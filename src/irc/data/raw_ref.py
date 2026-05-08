from __future__ import annotations

from dataclasses import dataclass

import duckdb

from irc.data.duckdb_helper import EXPECTED_TABLES


@dataclass(frozen=True)
class RawRef:
    source: str
    retrieved_at: str
    topic: str
    ref_id: str


def build_ref_id(source: str, topic: str, instrument_id: str, date: str) -> str:
    """Canonical raw_ref id used in DuckDB rows for reachability lookup."""
    return f"{source}:{topic}:{instrument_id}:{date}"


def ref_index_from_duckdb(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Collect all distinct _raw_ref values across tables that define this column."""
    # Single UNION ALL query instead of N+1 per-table queries
    union_sql = " UNION ALL ".join(
        f'SELECT DISTINCT _raw_ref FROM "{t}" WHERE _raw_ref IS NOT NULL'
        for t in EXPECTED_TABLES
    )
    rows = con.execute(union_sql).fetchall()
    return {row[0] for row in rows}


def is_reachable(ref: RawRef, index: set[str]) -> bool:
    """Pure reachability check against a prebuilt raw_ref index."""
    return ref.ref_id in index