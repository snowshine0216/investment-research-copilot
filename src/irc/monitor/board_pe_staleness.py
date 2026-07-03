"""Board-PE serve-while-stale + freshness states (ADR 0020 addendum 2026-07-03, OD-1).

Pure age/state math + a thin day-file scan edge, extracted so
industry_valuation.py (207 lines) stays inside its size budget (Q9). States:
FRESH (as_of == today — a date-string equality, calendar-INDEPENDENT per RD-3),
STALE (today's fetch failed; the newest NON-EMPTY cached table N ≤ 3 trading
days old — it FEEDS factor math, rendered with an explicit age tag), DARK
(nothing non-empty ≤ 3 td, or the trading calendar is unavailable on the
STALE BRANCH ONLY → per-stock industry_no_data, val_score == self_score).
RD-2: empty {} day files (the pre-light-up 2026-06-29/30 caches) are skipped by
the scan, never served under an age tag. Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_log = logging.getLogger(__name__)
MAX_STALE_TRADING_DAYS = 3
_DAY_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


@dataclass(frozen=True)
class BoardPeFreshness:
    state: str            # "FRESH" | "STALE" | "DARK"
    as_of: str | None     # source table date (named even for DARK when known)
    age_td: int | None    # trading-day age N; None when uncomputable


def freshness_dict(f: BoardPeFreshness | None) -> dict | None:
    """Pure: the {"state","as_of","age_td"} trace/panel projection (AC-11/AC-12)."""
    if f is None:
        return None
    return {"state": f.state, "as_of": f.as_of, "age_td": f.age_td}


def trading_day_age(as_of: str, today: str, trading_days) -> int | None:
    """Pure (AC-10): N = |{trading days d : as_of < d ≤ today}|. Weekend/holiday
    gaps count 0. None when either date is unparseable."""
    try:
        a, t = date.fromisoformat(as_of), date.fromisoformat(today)
    except (ValueError, TypeError):
        return None
    return sum(1 for d in trading_days if a < d <= t)


def read_day_table(cache_dir: Path, day: str) -> dict | None:
    """EDGE: parsed day file, or None (missing/unreadable → caller refetches)."""
    path = cache_dir / f"{day}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("board_pe_staleness: unreadable cache %s; skipping", path,
                     exc_info=True)
        return None


def write_day_table(cache_dir: Path, day: str, table: dict) -> None:
    """EDGE: byte-stable atomic day-file write (sorted keys, .tmp.{pid} → os.replace)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = (cache_dir / f"{day}.json").with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, cache_dir / f"{day}.json")


def nonempty_floats(table: object, path: Path) -> dict | None:
    """Pure guard: a non-empty dict of coercible-to-float values, else None. Any
    other shape (list, non-numeric value, torn write) → None (caller treats the
    day-file as ABSENT — never raises). Shared with industry_valuation.py's
    same-day cache-hit branch (round-1 P0 fix) so a corrupt cache degrades
    identically whether hit on the FRESH path or scanned on the stale path."""
    if not isinstance(table, dict) or not table:
        return None
    try:
        return {str(k): float(v) for k, v in table.items()}
    except (TypeError, ValueError):
        _log.warning("board_pe_staleness: malformed table %s; skipping", path)
        return None


def newest_nonempty(cache_dir: Path, today: str) -> tuple[str, dict] | None:
    """EDGE (RD-2): newest readable NON-EMPTY YYYY-MM-DD.json strictly before
    today; empty {} and unreadable files are SKIPPED and the scan continues to
    older files. None when nothing qualifies."""
    if not cache_dir.is_dir():
        return None
    days = sorted((p for p in cache_dir.iterdir()
                   if _DAY_FILE.match(p.name) and p.stem < today), reverse=True)
    for p in days:
        table = nonempty_floats(read_day_table(cache_dir, p.stem), p)
        if table is not None:
            return p.stem, table
    return None


def stale_fallback(cache_dir: Path, today: str, trading_days) -> tuple[dict, BoardPeFreshness]:
    """EDGE: today's fetch failed/empty → serve the newest non-empty cached table
    when its trading-day age N ≤ 3 (STALE — FEEDS factor math per OD-1). Calendar
    None/empty disables ONLY this branch (RD-3) → DARK with as_of named, age None.
    Nothing non-empty on disk → DARK(None, None). Never raises."""
    found = newest_nonempty(cache_dir, today)
    if found is None:
        return {}, BoardPeFreshness("DARK", None, None)
    as_of, table = found
    if not trading_days:                       # None or empty → honest N uncomputable
        return {}, BoardPeFreshness("DARK", as_of, None)
    age = trading_day_age(as_of, today, trading_days)
    if age is None or age > MAX_STALE_TRADING_DAYS:
        return {}, BoardPeFreshness("DARK", as_of, age)
    return table, BoardPeFreshness("STALE", as_of, age)
