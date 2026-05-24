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
    """Atomic batch upsert via named-column INSERT OR REPLACE + executemany.

    Rows are sorted (weight_pct DESC, holding_ticker ASC) before executemany
    so DuckDB's row insertion order is reproducible (AC15). `_raw_ref` uses
    build_ref_id(source, "fund_holdings", instrument_id, report_date) — shared
    across all holdings rows for the same (iid, report_date) (AC18).
    """
    materialised = tuple(rows)
    if not materialised:
        return 0
    ordered = sorted(
        materialised,
        key=lambda r: (-r.weight_pct, r.holding_ticker),
    )
    params = [
        [
            r.instrument_id,
            r.report_date,
            r.holding_ticker,
            r.holding_name,
            r.weight_pct,
            now_iso,
            r.source,
            build_ref_id(r.source, "fund_holdings", r.instrument_id, r.report_date),
        ]
        for r in ordered
    ]
    con.executemany(_UPSERT_SQL, params)
    return len(params)


def collect_holding_rows(
    instrument_id: str,
    asset_class: str,
    *,
    data_root: Path,
) -> tuple[tuple[HoldingRow, ...], str, str]:
    """Read holdings rows from item 003's ActiveFundSnapshot cache (primary)
    or fetch_cn_etf_holdings AkShare adapter (fallback, cn_etf only).

    Returns (rows, source, detail). detail values:
      - "loaded:{quarter}"           when a non-empty snapshot was used
      - "snapshot_empty"             when every available snapshot is empty
      - "snapshot_missing"           when no cache exists for this iid
      - "missing_report_date"        when snapshot.source_report_date is ""
      - "akshare_empty"              when AkShare returned no data
      - "fetched:{quarter}"          when AkShare returned valid data
      - "akshare_raised:{ExcType}"   defensive per F5
    """
    base = data_root / "fundamentals"
    candidates = sorted(base.glob(f"*/active_fund/fund_{instrument_id}.json"))
    saw_any_snapshot = False
    for path in reversed(candidates):
        quarter = path.parent.parent.name
        snap = load_active_fund_cache(instrument_id, quarter, data_root)
        if snap is None:
            continue
        saw_any_snapshot = True
        if not snap.constituent_analyses:
            # Empty snapshot — keep looking for an older non-empty one.
            continue
        if not snap.source_report_date:
            return (), "active_fund_snapshot", "missing_report_date"
        rows = tuple(
            HoldingRow(
                instrument_id=instrument_id,
                report_date=snap.source_report_date,
                holding_ticker=c.symbol,
                holding_name=c.name_cn,
                weight_pct=c.weight_pct,
                source="active_fund_snapshot",
            )
            for c in snap.constituent_analyses
            if c.symbol
        )
        return rows, "active_fund_snapshot", f"loaded:{quarter}"
    if saw_any_snapshot:
        return (), "active_fund_snapshot", "snapshot_empty"
    # No active-fund cache for this iid. cn_etf falls back to direct AkShare;
    # cn_equity_fund does NOT (item 003 owns the active-fund holdings cache).
    if asset_class != "cn_etf":
        return (), "active_fund_snapshot", "snapshot_missing"
    # F5: defensive try/except. fetch_cn_etf_holdings contract says it never
    # raises, but propagating an unexpected exception would crash the whole
    # ingest stage.
    try:
        result = fetch_cn_etf_holdings(instrument_id, top_n=10)
    except Exception as exc:
        return (), "akshare_cn_etf", f"akshare_raised:{type(exc).__name__}"
    if not result.constituents or not result.source_report_date:
        return (), "akshare_cn_etf", "akshare_empty"
    rows = tuple(
        HoldingRow(
            instrument_id=instrument_id,
            report_date=result.source_report_date,
            holding_ticker=h.symbol,
            holding_name=h.name_cn,
            weight_pct=h.weight_pct,
            source="akshare_cn_etf",
        )
        for h in result.constituents
        if h.symbol
    )
    return rows, "akshare_cn_etf", f"fetched:{result.source_report_quarter}"


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
    """I/O orchestration boundary: staleness check → collect → upsert.

    Pre-condition: caller MUST invoke ensure_schema(con) first (F6).
    ingest_one does not call it itself.

    Idempotent on same-day reruns (returns 'skipped_fresh' with rows_written=0
    when not stale). Never raises — failures are captured in IngestOutcome.
    `today_iso` is wall-clock CST (`_china_today()`); see AC20 / F1.
    """
    if asset_class not in _ELIGIBLE_ASSET_CLASSES:
        return IngestOutcome(
            instrument_id=instrument_id,
            status="skipped_no_data",
            report_date="",
            rows_written=0,
            detail=f"asset_class_not_eligible:{asset_class}",
        )
    if not force and not is_stale(
        con, instrument_id,
        today_iso=today_iso, threshold_days=threshold_days,
    ):
        return IngestOutcome(
            instrument_id=instrument_id, status="skipped_fresh",
            report_date="", rows_written=0, detail="fresh_within_threshold",
        )
    rows, _source, detail = collect_holding_rows(
        instrument_id, asset_class, data_root=data_root,
    )
    if not rows:
        status: Literal["skipped_no_data", "failed"] = (
            "failed" if detail.startswith("akshare_raised:") else "skipped_no_data"
        )
        return IngestOutcome(
            instrument_id=instrument_id, status=status,
            report_date="", rows_written=0, detail=detail,
        )
    n = upsert_holdings(con, rows, now_iso=now_iso)
    return IngestOutcome(
        instrument_id=instrument_id, status="wrote",
        report_date=rows[0].report_date, rows_written=n, detail="",
    )


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
