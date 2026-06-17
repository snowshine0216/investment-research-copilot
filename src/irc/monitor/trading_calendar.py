"""EDGE: cached CN (SSE) trading-calendar loader for the monitor nav_quality
gap check (spec §3.1). The ONLY monitor module besides akshare_client that
touches network/filesystem for the calendar. Degrades to None on any failure
so the pure gate can fall back to the calendar-day heuristic.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.data.akshare_client import fetch_trade_calendar
from irc.io_utils import atomic_write_text

_log = logging.getLogger(__name__)

_CACHE_REL = ("data", "monitor", "trade_calendar.json")


def _cache_path(root: Path) -> Path:
    return root.joinpath(*_CACHE_REL)


def _read_cache(path: Path, today: date) -> frozenset[date] | None:
    """Return cached trading days iff the cache is present AND fetched_on >= today
    AND the parsed set is non-empty.
    Returns None (→ caller refetches) on missing / stale / unparseable / empty cache."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if date.fromisoformat(obj["fetched_on"]) < today:
            return None
        days = frozenset(date.fromisoformat(d) for d in obj["dates"])
        if not days:
            return None
        return days
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _log.warning("trade_calendar cache unreadable (%s), refetching: %s", path, exc)
        return None


def _fetch_and_persist(path: Path, today: date) -> frozenset[date] | None:
    dates = sorted(fetch_trade_calendar())
    atomic_write_text(path, json.dumps(
        {"fetched_on": today.isoformat(), "dates": [d.isoformat() for d in dates]}))
    return frozenset(dates)


def load_trading_days(today: date, *, root: Path = Path(".")) -> frozenset[date] | None:
    """CN SSE trading days as a frozenset, cached at data/monitor/trade_calendar.json.
    Refetch only when the cache is missing or its fetched_on < today (once per
    calendar day; the calendar only appends at the tail). Returns None on any
    fetch/parse/write failure — the pure gate then falls back to max_gap_days."""
    path = _cache_path(root)
    cached = _read_cache(path, today)
    if cached is not None:
        return cached
    try:
        return _fetch_and_persist(path, today)
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the brief
        _log.warning("load_trading_days failed: %s", exc, exc_info=True)
        return None
