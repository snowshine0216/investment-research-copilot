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
    tables = con.execute(
        "SELECT table_name FROM information_schema.columns WHERE column_name='_raw_ref'"
    ).fetchall()
    out: set[str] = set()
    for (table_name,) in tables:
        if table_name not in EXPECTED_TABLES:
            continue
        rows = con.execute(f'SELECT DISTINCT _raw_ref FROM "{table_name}"').fetchall()
        out.update(row[0] for row in rows if row[0] is not None)
    return out


def is_reachable(ref: RawRef, index: set[str]) -> bool:
    """Pure reachability check against a prebuilt raw_ref index."""
    return ref.ref_id in index