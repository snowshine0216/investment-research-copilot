"""Ingest-stage writer for `index_valuation_history` (item 001 Phase 1a).

Effect at the edge: fetches each broad index's full PE/PB series via the
AkShare-only `fetch_cn_index_valuation_history` and upserts one row per
(index_key, date). Never fatal — a `None` history (unknown key / adapter
failure / empty frame) is skipped, not raised. This is the ONLY source the
opportunity stage reads for index valuation (no live fetch there — R3).
"""
from __future__ import annotations

from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory

_FetchFn = Callable[[str], IndexValuationHistory | None]


def ingest_index_valuation_history(
    con: duckdb.DuckDBPyConnection,
    index_keys: tuple[str, ...],
    *,
    fetch: _FetchFn = fetch_cn_index_valuation_history,
    now_iso: str,
    replace_keys: bool = False,
) -> int:
    """Upsert PE/PB history for each index_key. Returns rows written.

    `replace_keys=True` performs a per-key FULL REPLACE (D8): for any key whose
    fetch returns a NON-EMPTY history, DELETE that key's prior rows then insert
    the fresh full series. A None/empty fetch leaves existing rows untouched (no
    wipe on transient failure). Default `replace_keys=False` keeps append/upsert
    (the shared sector accumulate-forward leg).
    """
    params: list[list] = []
    keys_to_replace: list[str] = []
    for key in index_keys:
        hist = fetch(key)
        if hist is None or not hist.rows:
            continue
        if replace_keys:
            keys_to_replace.append(key)
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
    if not params:
        return 0
    con.execute("BEGIN")
    try:
        for key in keys_to_replace:
            con.execute(
                "DELETE FROM index_valuation_history WHERE index_key = ?", [key]
            )
        con.executemany(
            """
            INSERT OR REPLACE INTO index_valuation_history
                (index_key, date, pe_ttm, pb, dividend_yield,
                 _ingested_at, _source, _raw_ref)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(params)
