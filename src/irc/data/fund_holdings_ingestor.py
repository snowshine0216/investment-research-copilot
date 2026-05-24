"""Item 010 D B1 — fund_holdings DuckDB ingestor.

Pure-core module with thin I/O wrappers. Public surface:
- HoldingRow, IngestOutcome  : frozen dataclasses
- collect_holding_rows       : FS-read primitive (active-fund cache + cn_etf fallback)
- upsert_holdings            : DuckDB-write primitive (named-column INSERT OR REPLACE)
- is_stale                   : DuckDB-read primitive (staleness gate)
- ingest_one                 : I/O orchestration boundary (single instrument)
- ingest_many                : iterator over ingest_one (never raises)

Source of truth for holdings is item 003's ActiveFundSnapshot cache; the
fetch_cn_etf_holdings AkShare fallback fires ONLY for cn_etf instruments that
have no cached snapshot (per Q7). See docs/2026-05-22-thesis-cards-evidence-gap/
items/010-spec.md and 010-grill.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Literal

import duckdb

from irc.data.raw_ref import build_ref_id
from irc.fundamentals.akshare_fundamentals import fetch_cn_etf_holdings
from irc.fundamentals.snapshot_cache import load_active_fund_cache

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ELIGIBLE_ASSET_CLASSES: frozenset[str] = frozenset({"cn_equity_fund", "cn_etf"})
_VALID_SOURCES: frozenset[str] = frozenset(
    {"active_fund_snapshot", "akshare_cn_etf"}
)


@dataclass(frozen=True)
class HoldingRow:
    instrument_id: str
    report_date: str          # ISO YYYY-MM-DD
    holding_ticker: str
    holding_name: str
    weight_pct: float         # percent units 0.0–100.0
    source: str               # one of _VALID_SOURCES

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise ValueError("HoldingRow.instrument_id must be non-empty")
        if not _ISO_DATE_RE.fullmatch(self.report_date):
            raise ValueError(
                f"HoldingRow.report_date must match YYYY-MM-DD; got {self.report_date!r}"
            )
        if not self.holding_ticker:
            raise ValueError("HoldingRow.holding_ticker must be non-empty")
        if not (0.0 <= self.weight_pct <= 100.0):
            raise ValueError(
                f"HoldingRow.weight_pct must be in [0.0, 100.0]; got {self.weight_pct}"
            )
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"HoldingRow.source must be one of {sorted(_VALID_SOURCES)}; "
                f"got {self.source!r}"
            )


@dataclass(frozen=True)
class IngestOutcome:
    instrument_id: str
    status: Literal["wrote", "skipped_fresh", "skipped_no_data", "failed"]
    report_date: str          # "" when status != "wrote"
    rows_written: int         # 0 when status != "wrote"
    detail: str


# ── Public surface stubs (implemented in later tasks) ────────────────────────


def is_stale(
    con: duckdb.DuckDBPyConnection,
    instrument_id: str,
    *,
    today_iso: str,
    threshold_days: int = 30,
) -> bool:
    """Returns True iff fund_holdings has no rows for instrument_id OR the
    latest report_date is older than (today_iso - threshold_days) days.

    `today_iso` is wall-clock CST from `_china_today()` at the wire-in site
    (F1 / AC20); test callers pass an explicit ISO string. Pure DuckDB read.
    """
    result = con.execute(
        "SELECT MAX(report_date) FROM fund_holdings WHERE instrument_id = ?",
        [instrument_id],
    ).fetchone()
    if result is None or result[0] is None:
        return True
    latest = result[0]
    age = (date.fromisoformat(today_iso) - latest).days
    return age > threshold_days


_UPSERT_SQL = (
    "INSERT OR REPLACE INTO fund_holdings "
    "(instrument_id, report_date, holding_ticker, holding_name, "
    "weight_pct, _ingested_at, _source, _raw_ref) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


def upsert_holdings(
    con: duckdb.DuckDBPyConnection,
    rows: Iterable[HoldingRow],
    *,
    now_iso: str,
) -> int:
    raise NotImplementedError  # Task 3


def collect_holding_rows(
    instrument_id: str,
    asset_class: str,
    *,
    data_root: Path,
) -> tuple[tuple[HoldingRow, ...], str, str]:
    raise NotImplementedError  # Tasks 4-5


def ingest_one(
    con: duckdb.DuckDBPyConnection,
    instrument_id: str,
    asset_class: str,
    *,
    data_root: Path,
    today_iso: str,
    now_iso: str,
    threshold_days: int = 30,
    force: bool = False,
) -> IngestOutcome:
    raise NotImplementedError  # Task 7


def ingest_many(
    con: duckdb.DuckDBPyConnection,
    targets: Iterable[tuple[str, str]],
    *,
    data_root: Path,
    today_iso: str,
    now_iso: str,
    threshold_days: int = 30,
    force: bool = False,
) -> tuple[IngestOutcome, ...]:
    raise NotImplementedError  # Task 8
