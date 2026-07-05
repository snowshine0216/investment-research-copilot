"""Forward-ledger row builder (pure) + append (edge) — spec §5/D9, AC9.

One row per (date × board) with state ≠ quiet: {date, board_code, state,
composite_pctl, chg_pct, radar_version}. Append-only, atomic; a same-day rerun
does NOT duplicate (dedup by (date, board_code) already present). Corrupt/missing
existing file → treated as empty (never crash). Eval command deferred (F1).
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from pathlib import Path

from irc.rotation.types import BoardState

_log = logging.getLogger(__name__)


def build_ledger_rows(date: str, board_states: Iterable[BoardState],
                      radar_version: int) -> tuple[dict, ...]:
    """Pure: non-quiet board rows for the ledger."""
    return tuple(
        {"date": date, "board_code": b.board_code, "state": b.state,
         "composite_pctl": round(b.composite_pctl, 4), "chg_pct": round(b.mom20, 4),
         "radar_version": radar_version}
        for b in board_states if b.state != "quiet")


def _existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.is_file():
        return set()
    keys: set[tuple[str, str]] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            keys.add((obj.get("date"), obj.get("board_code")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("rotation ledger: unreadable %s; treating as empty", path,
                     exc_info=True)
        return set()
    return keys


def append_rows(path: Path, rows: Iterable[dict]) -> None:
    """EDGE: append-only atomic write; dedup by (date, board_code) (AC9)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_keys(path)
    fresh = [r for r in rows if (r["date"], r["board_code"]) not in existing]
    if not fresh:
        return
    prior = path.read_text(encoding="utf-8") if path.is_file() else ""
    body = prior + "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                           for r in fresh)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
