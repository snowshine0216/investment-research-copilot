"""EDGE: persisted board daily-series store (mirrors flow_series_store.py).

One file (data/rotation/board_series.json), keyed by board_code, pruned to
keep_td trading days, idempotent same-day (overwrite that board-day row), and
byte-stable (atomic_write_text: tmp→os.replace, sorted keys). Corrupt/missing →
{} (never crash). Snapshot rows carry price+flow+turnover; backfill rows carry
price(+turnover) only (kline has no flow) — flow5 tolerates None per §6.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path

from irc.io_utils import atomic_write_text
from irc.rotation.types import BoardDay

_log = logging.getLogger(__name__)


def _row(bd: BoardDay) -> dict:
    return asdict(bd)


def load_store(path: Path) -> dict[str, tuple[BoardDay, ...]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(code): tuple(BoardDay(**r) for r in rows)
                for code, rows in raw.items()}
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        _log.warning("rotation series_store: unreadable store %s; degrading", path,
                     exc_info=True)
        return {}


def _prune_window(anchor: str, keep_td: int, trading_days: Iterable[str]) -> set[str] | None:
    days = sorted(trading_days)
    if not days:
        return None
    eligible = [d for d in days if d <= anchor]
    return set(eligible[-keep_td:])


def _prune(rows: tuple[BoardDay, ...], anchor: str, keep_td: int,
           trading_days: Iterable[str]) -> tuple[BoardDay, ...]:
    keep = _prune_window(anchor, keep_td, trading_days)
    kept = [r for r in rows if keep is None or r.date in keep]
    return tuple(sorted(kept, key=lambda r: r.date))


def _merge_day(prior: tuple[BoardDay, ...], bd: BoardDay) -> tuple[BoardDay, ...]:
    return tuple(r for r in prior if r.date != bd.date) + (bd,)


def _write(path: Path, store: Mapping[str, tuple[BoardDay, ...]]) -> None:
    payload = {code: [_row(r) for r in sorted(rows, key=lambda x: x.date)]
               for code, rows in sorted(store.items())}
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2,
                                       sort_keys=True))


def append_snapshot(path: Path, day_rows: Iterable[BoardDay], *, keep_td: int,
                    trading_days: Iterable[str]) -> dict[str, tuple[BoardDay, ...]]:
    store = load_store(path)
    trading_days = tuple(trading_days)
    anchor = ""
    for bd in day_rows:
        anchor = max(anchor, bd.date)
        merged = _merge_day(store.get(bd.board_code, ()), bd)
        store[bd.board_code] = _prune(merged, bd.date, keep_td, trading_days)
    _write(path, store)
    return store


def seed_backfill(path: Path, backfilled: Mapping[str, Iterable[BoardDay]], *,
                  keep_td: int, trading_days: Iterable[str]
                  ) -> dict[str, tuple[BoardDay, ...]]:
    store = load_store(path)
    trading_days = tuple(trading_days)
    anchor = max((r.date for rows in backfilled.values() for r in rows), default="")
    for code, rows in backfilled.items():
        by_date = {r.date: r for r in store.get(code, ())}
        by_date.update({r.date: r for r in rows})
        store[code] = _prune(tuple(by_date.values()), anchor, keep_td, trading_days)
    _write(path, store)
    return store
