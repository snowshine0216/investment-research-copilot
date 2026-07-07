"""EDGE + pure merge: cross-day stock→东财行业 store (ADR 0020 addendum 2026-07-03).

data/monitor/stock_industry_map.json = {symbol: {"industry": str, "seen_at":
"YYYY-MM-DD"}}. Filled batch-first from the f100 field (行业) riding the ONE daily
ulist.np call (both call sites: 12:15 brief + 15:45 capture); per-symbol
fallback results merge too (Q3). NB: f100 in ulist.np — NOT f127, which is
numeric there; the per-symbol stock/get fallback correctly uses its own f127.
Refresh-on-seen; serve-while-stale ≤ 30
CALENDAR days — deliberately NOT trading days (industry membership is
quasi-static; see CONTEXT.md 'Stock-industry map (cross-day store)').
Absence ≠ evidence: None/blank never written (RD-4 — a throttle classifies
TRANSIENT upstream and can never reach here as a string). Corrupt/missing →
{} (never crash the brief). Byte-stable atomic writes; a no-op merge writes
nothing. Patterned on flow_series_store.py.

Also serves the sector rotation radar (ADR 0023 D7): the SAME store holds 东财
行业 NAMES (f100) in the `industry` slot for BOTH consumers (monitor and radar) —
never board codes. The radar translates 行业 name → EM board code at its OWN join
(`rotation._cmd_helpers.resolve_candidates`, via a `{board_name: board_code}` map
built from that run's `BoardState` list), never in the store, which stays
monitor-owned and name-based. 30-day serve-while-stale semantics preserved —
extended in place, not forked.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.io_utils import atomic_write_text

_log = logging.getLogger(__name__)
MAX_AGE_DAYS = 30


def _valid_row(row: object) -> bool:
    return (isinstance(row, dict) and isinstance(row.get("industry"), str)
            and isinstance(row.get("seen_at"), str))


def load_store(path: Path) -> dict[str, dict]:
    """Load the store; missing/corrupt file → {} with a WARNING; malformed rows
    dropped, never served (same degrade posture as flow_series_store.load_store)."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("industry_map_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}
    if not isinstance(raw, dict):
        _log.warning("industry_map_store: non-dict store %s; degrading", path)
        return {}
    out: dict[str, dict] = {}
    for sym, row in raw.items():
        if _valid_row(row):
            out[str(sym)] = {"industry": row["industry"], "seen_at": row["seen_at"]}
        else:
            _log.warning("industry_map_store: malformed row for %s; dropped", sym)
    return out


def merge_seen(store: dict, today: str, industry_by_symbol: dict) -> dict[str, dict]:
    """Pure (NEW dict, no mutation): upsert every non-None, non-blank industry as
    {industry, seen_at: today}. REFRESH-ON-SEEN: seen_at refreshes even when the
    industry string is unchanged. None/blank skipped (absence ≠ evidence)."""
    fresh = {
        str(sym): {"industry": ind.strip(), "seen_at": today}
        for sym, ind in industry_by_symbol.items()
        if isinstance(ind, str) and ind.strip()
    }
    return {**store, **fresh}


def _within(seen_at: str, today: str, max_age_days: int) -> bool:
    try:
        delta = (date.fromisoformat(today) - date.fromisoformat(seen_at)).days
    except ValueError:
        return False   # unparseable seen_at → dropped, not served
    # Round-1 P2 hardening: a future seen_at (clock skew / bad write) yields a
    # negative delta that would otherwise always be <= max_age_days → served
    # fresh forever. Only 0 <= delta <= max_age_days counts as fresh; negative
    # falls out of fresh_slice (the per-symbol fallback then handles it).
    return 0 <= delta <= max_age_days


def fresh_slice(store: dict, today: str, max_age_days: int = MAX_AGE_DAYS) -> dict[str, str]:
    """Pure: {symbol: industry} for rows seen within ≤ max_age_days CALENDAR days
    of today (Q4 — quasi-static attribute, NOT a market-data freshness window)."""
    return {sym: row["industry"] for sym, row in store.items()
            if _within(row.get("seen_at", ""), today, max_age_days)}


def record_seen(path: Path, today: str, industry_by_symbol: dict) -> dict[str, dict]:
    """EDGE: load → merge → byte-stable atomic write → merged store. A no-op merge
    (e.g. an all-None fallback result) writes NOTHING — the file is not even
    created (RD-4)."""
    store = load_store(path)
    merged = merge_seen(store, today, industry_by_symbol)
    if merged != store:
        atomic_write_text(path, json.dumps(merged, ensure_ascii=False, indent=2,
                                           sort_keys=True))
    return merged
