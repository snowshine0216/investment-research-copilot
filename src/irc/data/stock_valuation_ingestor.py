"""Ingest-stage writer for `stock_valuation_history` (Phase D PR1).

Effect at the edge: upserts each A-share's full PE/PB series into
`stock_valuation_history`, recording `_source` per row. Never fatal at the
batch boundary — a `None` result from `fetch` (miss / adapter failure / empty
frame) is skipped, not raised. Mirrors `index_valuation_ingestor.py`. This
cached table is the ONLY source the opportunity stage reads for per-stock
valuation (no live fetch there — spec §3.7).
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.stock_valuation_types import StockValuationHistory

_FetchFn = Callable[[str], "tuple[StockValuationHistory, str] | None"]

_UPSERT_SQL = """
INSERT OR REPLACE INTO stock_valuation_history
    (stock_code, date, pe_ttm, pb, dividend_yield, _ingested_at, _source, _raw_ref)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def is_stock_valuation_stale(
    con: duckdb.DuckDBPyConnection,
    stock_code: str,
    *,
    today_iso: str,
    threshold_days: int = 30,
) -> bool:
    """True iff stock_valuation_history has no rows for stock_code OR the latest
    date is older than (today_iso - threshold_days) days. Mirrors
    fund_holdings_ingestor.is_stale. Pure DuckDB read."""
    result = con.execute(
        "SELECT MAX(date) FROM stock_valuation_history WHERE stock_code = ?",
        [stock_code],
    ).fetchone()
    if result is None or result[0] is None:
        return True
    age = (date.fromisoformat(today_iso) - result[0]).days
    return age > threshold_days


def _build_params(
    code: str, hist: StockValuationHistory, source: str, now_iso: str
) -> list[list]:
    """Pure: build the list of upsert param rows for one stock history."""
    return [
        [
            code,
            pt.date_iso,
            pt.pe_ttm,
            pt.pb,
            pt.dividend_yield,
            now_iso,
            source,
            build_ref_id(source, "stock_valuation_history", code, pt.date_iso),
        ]
        for pt in hist.rows
    ]


def ingest_stock_valuation_history(
    con: duckdb.DuckDBPyConnection,
    stock_codes: tuple[str, ...],
    *,
    fetch: _FetchFn,
    now_iso: str,
) -> int:
    """Upsert PE/PB history for each stock_code, recording the per-row _source.
    `fetch(code)` returns (history, source) where source ∈ {eastmoney, tushare},
    or None on a miss. Returns rows written. Atomic at the batch boundary."""
    params: list[list] = []
    for code in stock_codes:
        result = fetch(code)
        if result is None:
            continue
        hist, source = result
        params.extend(_build_params(code, hist, source, now_iso))
    if params:
        con.execute("BEGIN")
        try:
            con.executemany(_UPSERT_SQL, params)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return len(params)
