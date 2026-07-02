"""EDGE: persisted completed-day-only flow daily-series store (B2 §5.C, D6/D7).

One market-wide file (data/monitor/fund_flow_series.json), scoped to the monitored
union symbols, pruned to ~25 trading days. The append API takes only COMPLETED
days — the 12:15 brief path has NO write access (provisional f184 is render-only,
D6/trap §8). Idempotent same-day (overwrite that day's row). Byte-stable
(atomic_write_text: tmp→os.replace, sorted keys, 4dp). Corrupt/missing → {}
(never crash).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from irc.io_utils import atomic_write_text
from irc.monitor.flow_fetch import FlowSeries

_log = logging.getLogger(__name__)
_ROUND_DP = 4


def load_store(path: Path) -> dict[str, FlowSeries]:
    """Load the store; degrade to {} on corrupt/missing (never crash)."""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(sym): tuple((str(d), float(v)) for d, v in rows)
                for sym, rows in raw.items()}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        _log.warning("flow_series_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}


def series_slice(
    store: Mapping[str, FlowSeries], symbols: Iterable[str]
) -> dict[str, FlowSeries | None]:
    """Per-symbol slice for a run: missing symbol → None (uncovered)."""
    return {s: store.get(s) for s in dict.fromkeys(symbols)}


def _prune_window(anchor: str, keep_td: int, trading_days: Iterable[str]) -> set[str] | None:
    """Pure: the last keep_td trading days at-or-before anchor. None → no pruning
    (empty/absent calendar degrades to "keep everything")."""
    days = sorted(trading_days)
    if not days:
        return None
    eligible = [d for d in days if d <= anchor]
    return set(eligible[-keep_td:])


def _prune(rows: FlowSeries, anchor: str, keep_td: int, trading_days: Iterable[str]) -> FlowSeries:
    """Pure: keep only rows whose date is in the last keep_td trading_days
    at-or-before anchor (the day just written)."""
    keep = _prune_window(anchor, keep_td, trading_days)
    kept = [(d, v) for d, v in rows if keep is None or d in keep]
    return tuple(sorted(kept, key=lambda r: r[0]))


def _write(path: Path, store: Mapping[str, FlowSeries]) -> None:
    payload = {sym: [[d, round(v, _ROUND_DP)] for d, v in rows]
               for sym, rows in sorted(store.items())}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _merge_day(prior: FlowSeries, today: str, value: float) -> FlowSeries:
    """Pure: overwrite today's row if present (idempotent), else append."""
    return tuple((d, v) for d, v in prior if d != today) + ((today, float(value)),)


def append_today(
    path: Path,
    today: str,
    today_by_symbol: Mapping[str, float | None],
    *,
    keep_td: int,
    trading_days: Iterable[str],
) -> dict[str, FlowSeries]:
    """Append COMPLETED-day rows (idempotent same-day; None values skipped),
    prune to keep_td trading days, byte-stable write. Returns the pruned store."""
    store = load_store(path)
    trading_days = tuple(trading_days)
    for sym, val in today_by_symbol.items():
        if val is None:
            continue
        merged = _merge_day(store.get(sym, ()), today, val)
        store[sym] = _prune(merged, today, keep_td, trading_days)
    _write(path, store)
    return store


def _ok_series_from_day_file(day_payload: Mapping[str, dict]) -> dict[str, FlowSeries]:
    """Pure: fund_flow/<date>.json payload → {symbol: FlowSeries} for status=ok only."""
    out: dict[str, FlowSeries] = {}
    for sym, entry in day_payload.items():
        if entry.get("status") != "ok":
            continue
        out[sym] = tuple(
            (str(r["date"]), float(r["main_net_pct"])) for r in entry.get("rows", [])
        )
    return out


def _load_day_file(f: Path) -> dict[str, FlowSeries]:
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return _ok_series_from_day_file(payload)


def seed_from_per_symbol(
    path: Path,
    fund_flow_dir: Path,
    *,
    keep_td: int,
    trading_days: Iterable[str],
) -> dict[str, FlowSeries]:
    """D7: one-time merge of existing fund_flow/*.json `ok` series into the store."""
    store = load_store(path)
    trading_days = tuple(trading_days)
    anchor = max(trading_days) if trading_days else ""
    if fund_flow_dir.is_dir():
        for f in sorted(fund_flow_dir.glob("*.json")):
            for sym, rows in _load_day_file(f).items():
                merged = {d: v for d, v in store.get(sym, ())}
                merged.update(dict(rows))
                store[sym] = _prune(tuple(merged.items()), anchor, keep_td, trading_days)
    _write(path, store)
    return store
