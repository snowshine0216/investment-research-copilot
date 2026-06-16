"""nav_history.jsonl — the authoritative dense NAV series for the M3 backtest.

The signal ledger is run-sampled (sparse, duplicate as_of_date); NAV outcomes
come from THIS file. Producer (EDGE, in irc monitor) appends a bounded trailing
window per run; reader (PURE) dedups + re-sorts. Append-only JSONL, prefix-valid
(crash may truncate the final line only). Mirrors forward_log.py.

Row schema: {fund_id, nav_date, nav_acc, written_at, source_run_date}
  nav_acc is COALESCE(nav_acc, nav) — same perf basis as the ledger / eval_trace.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavHistoryRow:
    fund_id: str
    nav_date: str
    nav_acc: float
    written_at: str
    source_run_date: str


def parse_nav_history_lines(text: str) -> list[NavHistoryRow]:
    """PURE: parse JSONL text → rows, skipping any unparseable (truncated) line
    with a logged warning. The file is a valid prefix: a crash mid-write can only
    truncate the final line."""
    rows: list[NavHistoryRow] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            rows.append(NavHistoryRow(
                fund_id=obj["fund_id"], nav_date=obj["nav_date"],
                nav_acc=obj["nav_acc"], written_at=obj["written_at"],
                source_run_date=obj["source_run_date"],
            ))
        except Exception:  # noqa: BLE001 — skip a truncated/corrupt line, never crash
            _log.warning("skipping unparseable nav_history line: %r", line[:80])
    return rows


def latest_per_nav_date(rows: list[NavHistoryRow]) -> list[NavHistoryRow]:
    """PURE: dedup by (fund_id, nav_date). Tiebreak chain (total order →
    byte-stable): written_at desc → source_run_date desc → last line in file wins.
    Then sort ascending by (fund_id, nav_date)."""
    best: dict[tuple[str, str], tuple[str, str, NavHistoryRow]] = {}
    for row in rows:
        key = (row.fund_id, row.nav_date)
        cand = (row.written_at, row.source_run_date, row)
        cur = best.get(key)
        # >= so the LATER line wins on a full (written_at, source_run_date) tie.
        if cur is None or (cand[0], cand[1]) >= (cur[0], cur[1]):
            best[key] = cand
    out = [v[2] for v in best.values()]
    return sorted(out, key=lambda r: (r.fund_id, r.nav_date))


def _date_minus_days(run_date: str, days: int) -> str:
    return (date.fromisoformat(run_date) - timedelta(days=days)).isoformat()


def nav_history_append_rows(
    *, fund_id: str, acc_series: tuple[tuple[str, float], ...],
    run_date: str, written_at: str, nav_append_days: int,
) -> list[NavHistoryRow]:
    """PURE: build the bounded trailing-window rows for one fund's run.

    Keeps only nav_date >= run_date - nav_append_days (calendar days) so per-run
    growth is capped (7 funds x ~40 dates) instead of O(runs x full_history).
    The one-time backfill seeds the pre-window history."""
    cutoff = _date_minus_days(run_date, nav_append_days)
    return [
        NavHistoryRow(
            fund_id=fund_id, nav_date=nav_date, nav_acc=float(nav_acc),
            written_at=written_at, source_run_date=run_date,
        )
        for nav_date, nav_acc in acc_series
        if nav_date >= cutoff
    ]


def append_nav_history(path: Path, rows: list[NavHistoryRow]) -> None:
    """EDGE: prefix-valid append. open O_APPEND, one os.write per row (encoded
    bytes), one os.fsync after the batch. Failures logged + swallowed — never
    crash the brief. NOT 'atomic' — the safe contract is prefix-validity."""
    if not rows:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            for row in rows:
                payload = (json.dumps({
                    "fund_id": row.fund_id, "nav_date": row.nav_date,
                    "nav_acc": row.nav_acc, "written_at": row.written_at,
                    "source_run_date": row.source_run_date,
                }, ensure_ascii=False) + "\n").encode("utf-8")
                os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("append_nav_history failed for %s", path, exc_info=True)
