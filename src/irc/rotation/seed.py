"""EDGE orchestration for `irc rotation seed` (spec §4 seed steps, D11, AC2).

Resumable + partial-tolerant: each step skips anything already cached and reports
a coverage summary; a transient failure on one board/fund/chunk never aborts the
rest (breaker-protected via the injected fetchers). No LLM, no paid search.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from irc.rotation.board_fetch import fetch_board_hist
from irc.rotation.composite import MIN_TD
from irc.rotation.series_store import load_store, seed_backfill

_log = logging.getLogger(__name__)


def seed_boards(
    board_list: Iterable[tuple[str, str]],
    *,
    series_path: Path,
    keep_td: int,
    trading_days,
    fetch_hist=fetch_board_hist,
) -> dict:
    """Backfill board-history series; skip boards already having ≥MIN_TD rows (AC2)."""
    store = load_store(series_path)
    done, skipped, failed = 0, 0, []
    for code, name in board_list:
        if len(store.get(code, ())) >= MIN_TD:
            skipped += 1
            continue
        try:
            rows = fetch_hist(code, name)
        except Exception as exc:  # noqa: BLE001 — partial-tolerant (AC2/T3)
            _log.warning("seed_boards: %s failed: %s", code, exc)
            failed.append(code)
            continue
        if rows:
            seed_backfill(series_path, {code: rows}, keep_td=keep_td,
                          trading_days=trading_days)
            done += 1
        else:
            failed.append(code)
    return {"done": done, "skipped": skipped, "failed": tuple(failed)}


def seed_holdings(fund_ids: Iterable[str], *, cache_dir: Path, fetch) -> dict:
    """Fetch top-10 holdings for funds missing from the cache; skip cached ones (AC2)."""
    done, skipped, failed = 0, 0, []
    for fid in fund_ids:
        if (cache_dir / f"{fid}.json").is_file():
            skipped += 1
            continue
        try:
            fetch(fid, cache_dir=cache_dir)
            done += 1
        except Exception as exc:  # noqa: BLE001 — never raises (fetch_top_holdings doesn't)
            _log.warning("seed_holdings: %s failed: %s", fid, exc)
            failed.append(fid)
    return {"done": done, "skipped": skipped, "failed": tuple(failed)}


def seed_stock_board_map(
    symbols: Iterable[str],
    *,
    map_path: Path,
    today: str,
    batch_fetch,
    load_existing,
    record,
    chunk_size: int = 200,
) -> dict:
    """Chunked ulist.np (f100 行业 — NOT f127, T1) over held stocks; skip symbols
    already present in the map. record(map_path, today, industry_by_symbol) merges
    each chunk through the extended industry_map_store. Partial-tolerant (AC2)."""
    existing = load_existing(map_path)
    fresh = set(existing.keys())
    pending = [s for s in dict.fromkeys(symbols) if s not in fresh]
    done, failed = 0, []
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i:i + chunk_size]
        try:
            _flow, industry_by_symbol = batch_fetch(tuple(chunk))
        except Exception as exc:  # noqa: BLE001 — partial-tolerant chunk (AC2/T3)
            _log.warning("seed_stock_board_map: chunk failed: %s", exc)
            failed.extend(chunk)
            continue
        record(map_path, today, industry_by_symbol)
        done += sum(1 for v in industry_by_symbol.values() if v)
    return {"done": done, "skipped": len(fresh), "failed": tuple(failed)}
