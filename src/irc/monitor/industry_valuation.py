"""EDGE + pure parse: monitor industry valuation leg (ADR 0020 / ADR 0021).

Two cached/day reads, mirroring flow_fetch.py's contract (never raises, parsed
rows, per-day JSON cache, light pacing). Default fetch is wired to
`irc.monitor.em_raw`'s raw-JSON EastMoney fetchers (CN-egress light-up,
routed through IRC_CN_PROXY when configured — no akshare wrapper on this
leg; `fetch` stays injectable for tests):

- `fetch_board_pe_frame` — paginated market-wide call → 东财 industry → avg PE.
- `fetch_stock_info_frame(symbol)` — per-symbol → the symbol's 东财 industry
  (~15-25 deduped cached calls/run, same volume + contract as flow_fetch).

Industry-average PE is from a single 市盈率 column (cap-weighting unverified at
the source; see ADR 0020 denominator-robustness risk). NON-positive / NaN PE →
dropped (→ industry_no_data per-stock). No DataFrame on disk; the cache stores
parsed primitives so the on-disk form is byte-stable. An empty board-PE parse
is returned but never cached (D3) — a soft-throttle empty page doesn't freeze
the leg dark for the day.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from irc.monitor.board_pe_staleness import (
    BoardPeFreshness, nonempty_floats, read_day_table, stale_fallback, write_day_table,
)
from irc.monitor.cached_fetch import DEAD, OK, TRANSIENT, Outcome, cache_first_fetch
from irc.monitor.em_raw import fetch_board_pe_frame, fetch_stock_info_frame

_log = logging.getLogger(__name__)

_PE_NAME_COL = "板块名称"
_PE_VALUE_COL = "市盈率"
_INFO_ITEM_COL = "item"
_INFO_VALUE_COL = "value"
_INDUSTRY_ITEM = "行业"


def _coerce_positive(value: object) -> float | None:
    """Pure: finite strictly-positive float, else None. A non-positive or NaN PE
    is meaningless as a denominator → None (→ industry_no_data upstream)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f) or f <= 0.0:
        return None
    return f


def parse_industry_pe(df: pd.DataFrame | None) -> dict[str, float]:
    """Pure: market-wide board table → {industry_name: avg_pe}. Rows with a
    non-positive / NaN / non-numeric 市盈率 are dropped. Unexpected shape → {}."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    if _PE_NAME_COL not in df.columns or _PE_VALUE_COL not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        pe = _coerce_positive(row[_PE_VALUE_COL])
        if pe is None:
            continue
        out[str(row[_PE_NAME_COL]).strip()] = pe
    return out


def parse_stock_industry(df: pd.DataFrame | None) -> str | None:
    """Pure: stock_individual_info_em (item,value) long table → the 行业 value,
    or None. Unexpected shape / missing 行业 row → None (→ no industry leg)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if _INFO_ITEM_COL not in df.columns or _INFO_VALUE_COL not in df.columns:
        return None
    for _, row in df.iterrows():
        if str(row[_INFO_ITEM_COL]).strip() == _INDUSTRY_ITEM:
            text = str(row[_INFO_VALUE_COL]).strip()
            return text or None
    return None


def fetch_industry_pe(
    *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
    trading_days: frozenset | None = None,
) -> tuple[dict[str, float], BoardPeFreshness]:
    """EDGE: ONE market-wide board PE call/day, cached (D3: empty parse never
    cached). Returns (table, BoardPeFreshness). FRESH iff as_of == today —
    calendar-INDEPENDENT (RD-3); otherwise the board_pe_staleness stale branch
    (STALE ≤3 td FEEDS factor math per OD-1; DARK otherwise or when trading_days
    is None/empty). NEVER raises; fetch injectable (default wraps
    em_raw.fetch_board_pe_frame, raw JSON via IRC_CN_PROXY, D3)."""
    day_path = cache_dir / f"{today}.json"
    cached = read_day_table(cache_dir, today)
    if cached is not None:
        table = nonempty_floats(cached, day_path)
        if table is None:
            # Round-1 P0 fix: a non-dict / non-numeric same-day cache (torn write,
            # schema drift) must NOT raise and must NOT be silently indistinguishable
            # from "never fetched" — treat the day-file as ABSENT and fall through to
            # the normal fetch → stale_fallback chain below.
            _log.warning("industry_valuation: corrupt same-day board-PE cache %s — "
                         "ignoring", day_path)
        else:
            return table, BoardPeFreshness("FRESH", today, 0)
    if fetch is None:
        fetch = lambda: fetch_board_pe_frame(sleep=sleep)  # noqa: E731 — raw JSON via proxy (D3)
    parsed: dict[str, float] = {}
    try:
        parsed = parse_industry_pe(fetch())
    except Exception:  # noqa: BLE001 — degrade to the stale branch, never crash
        _log.warning("industry_valuation: board PE fetch failed", exc_info=True)
    if parsed:                       # D3: never cache an empty parse (F4 wart)
        write_day_table(cache_dir, today, parsed)
        return parsed, BoardPeFreshness("FRESH", today, 0)
    return stale_fallback(cache_dir, today, trading_days)


def _industry_cache_payload(by_symbol: dict[str, str | None]) -> dict[str, dict]:
    """Pure: symbol→industry map → deterministic cache dict (sorted symbols).
    None → status:miss (confirmed: the endpoint answered with no 行业 row).
    Transient (raised) fetches never reach here — they are not persisted."""
    return {
        symbol: ({"status": "ok", "industry": by_symbol[symbol]}
                 if by_symbol[symbol] is not None
                 else {"status": "miss", "industry": None})
        for symbol in sorted(by_symbol)
    }


_RECOGNISED_STATUSES = ("ok", "miss")  # the only values _industry_cache_payload writes


def _load_industry_cache(payload: dict[str, dict]) -> dict[str, str | None]:
    """Pure: cache dict → symbol→(industry|None) map. ok→industry, miss→None. An
    UNRECOGNISED status (only reachable via external corruption / a manual edit)
    is OMITTED → the symbol reads as cache-absent → refetched, never served as a
    frozen confirmed miss (Line-23 residual fix)."""
    out: dict[str, str | None] = {}
    for symbol, entry in payload.items():
        status = entry.get("status")
        if status not in _RECOGNISED_STATUSES:
            _log.warning("industry_valuation: unrecognised cache status %r for %s; "
                         "refetching", status, symbol)
            continue
        out[symbol] = entry.get("industry") if status == "ok" else None
    return out


def _is_blank_info_frame(df: object) -> bool:
    """Pure: True when the fetch returned NO usable frame — None / not a frame /
    empty / missing the item/value columns. This is the soft-throttle empty-200
    signature, structurally distinct from a well-formed (item,value) table that
    genuinely lacks a 行业 row → TRANSIENT, not a confirmed miss (ADR 0019
    2026-06-22 addendum refinement)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return True
    return _INFO_ITEM_COL not in df.columns or _INFO_VALUE_COL not in df.columns


def _classify_industry(symbol: str, fetch) -> Outcome:
    """EDGE: classify one symbol's fetch (NEVER sleeps — cached_fetch owns pacing).
    Raised fetch OR a blank/throttled frame → TRANSIENT (retried, not cached); a
    well-formed table with no 行业 row → DEAD (cached miss); a parsed industry →
    OK. CN endpoint DIRECT."""
    try:
        df = fetch(symbol=symbol)
    except Exception:  # noqa: BLE001 — degrade to TRANSIENT (retry), never crash
        _log.warning("industry_valuation: stock_individual_info_em failed for %s",
                     symbol, exc_info=True)
        return TRANSIENT, None
    if _is_blank_info_frame(df):  # blank/throttled 200 body → retry, never freeze
        _log.warning("industry_valuation: blank/throttled frame for %s; transient",
                     symbol)
        return TRANSIENT, None
    industry = parse_stock_industry(df)
    return (OK, industry) if industry is not None else (DEAD, None)


def fetch_stock_industry_map(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str,
    fetch=None, sleep=time.sleep,
) -> dict[str, str | None]:
    """EDGE: dedup symbols → cache-first per-day per-symbol fetch (cached_fetch) →
    byte-stable write of ok+dead only. Idempotent within a day for settled symbols;
    transient throttles retry next run. Same contract + volume as
    flow_fetch.fetch_flow_series. fetch injectable; default wraps
    em_raw.fetch_stock_info_frame (raw JSON via proxy, D3)."""
    if fetch is None:
        fetch = lambda symbol: fetch_stock_info_frame(symbol)  # noqa: E731 — raw JSON (D3)
    return cache_first_fetch(
        symbols, cache_dir=cache_dir, today=today,
        fetch_one=lambda symbol: _classify_industry(symbol, fetch),
        serialize=_industry_cache_payload, deserialize=_load_industry_cache, sleep=sleep,
    )
