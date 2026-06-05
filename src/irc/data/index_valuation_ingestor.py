"""Ingest-stage writer for `index_valuation_history` (item 001 Phase 1a).

Effect at the edge: fetches each broad index's full PE/PB series via the
AkShare-only `fetch_cn_index_valuation_history` and upserts one row per
(index_key, date). Never fatal — a `None` history (unknown key / adapter
failure / empty frame) is skipped, not raised. This is the ONLY source the
opportunity stage reads for index valuation (no live fetch there — R3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Callable

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_index_valuation import fetch_cn_index_valuation_history
from irc.fundamentals.index_valuation_types import IndexValuationHistory
from irc.opportunity.lookthrough_valuation import MIN_PE_DAYS, MIN_PE_POINTS
from irc.opportunity.sector_indices import SECTOR_INDEX_KEYS

_FetchFn = Callable[[str], IndexValuationHistory | None]


def ingest_index_valuation_history(
    con: duckdb.DuckDBPyConnection,
    index_keys: tuple[str, ...],
    *,
    fetch: _FetchFn = fetch_cn_index_valuation_history,
    now_iso: str,
) -> int:
    """Upsert PE/PB history for each index_key. Returns rows written."""
    params: list[list] = []
    for key in index_keys:
        hist = fetch(key)
        if hist is None:
            continue
        for pt in hist.rows:
            params.append([
                key, pt.date_iso, pt.pe_ttm, pt.pb, pt.dividend_yield,
                now_iso, "akshare",
                build_ref_id("akshare", "index_valuation_history", key, pt.date_iso),
            ])
    if params:
        con.execute("BEGIN")
        try:
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


@dataclass(frozen=True)
class SectorIngestAudit:
    """Per-slug accumulation status for the B1 ingest-audit artifact."""
    slug: str
    row_count: int
    has_numeric_pe: bool
    points: int           # non-null PE points (the MIN_PE_POINTS axis)
    latest_date: str | None
    freshness_days: int | None
    span_days: int        # latest - earliest non-null PE date (MIN_PE_DAYS axis)
    mature: bool          # points >= MIN_PE_POINTS AND span_days >= MIN_PE_DAYS


def _audit_one_slug(
    con: duckdb.DuckDBPyConnection, slug: str, *, today: _date
) -> SectorIngestAudit:
    df = con.execute(
        "SELECT CAST(date AS VARCHAR) AS d, pe_ttm FROM index_valuation_history "
        "WHERE index_key = ? ORDER BY date",
        [slug],
    ).fetchdf()
    row_count = int(len(df))
    pe_dates = [
        r["d"] for _, r in df.iterrows() if r["pe_ttm"] is not None and r["pe_ttm"] == r["pe_ttm"]
    ]
    points = len(pe_dates)
    latest_date = pe_dates[-1] if pe_dates else None
    freshness_days = (
        (today - _date.fromisoformat(latest_date)).days if latest_date else None
    )
    span_days = (
        (_date.fromisoformat(pe_dates[-1]) - _date.fromisoformat(pe_dates[0])).days
        if points >= 2 else 0
    )
    mature = points >= MIN_PE_POINTS and span_days >= MIN_PE_DAYS
    return SectorIngestAudit(
        slug=slug, row_count=row_count, has_numeric_pe=points > 0, points=points,
        latest_date=latest_date, freshness_days=freshness_days, span_days=span_days,
        mature=mature,
    )


def audit_sector_ingest(
    con: duckdb.DuckDBPyConnection, *, today: _date | None = None
) -> tuple[SectorIngestAudit, ...]:
    """Per-slug accumulation audit over ALL sector slugs (replaces the
    ingestor's silent aggregate count). Returns one row per slug, sorted by
    slug. B1 expected state: every slug present, 0 mature -> 0 grounded."""
    ref = today or _date.today()
    return tuple(
        _audit_one_slug(con, slug, today=ref) for slug in sorted(SECTOR_INDEX_KEYS)
    )
