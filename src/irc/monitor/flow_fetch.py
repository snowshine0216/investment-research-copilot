"""EDGE + pure parse: monitor capital-flow leg via AkShare (ADR 0019).

`ak.stock_individual_fund_flow(stock, market)` returns ONE per-symbol daily
table (主力净流入-净占比 percent-points). Unlike `fund_purchase_em` there is NO
batch variant — flow is ~15-25 SEQUENTIAL per-A-share-symbol calls/run, deduped
and cached per day. Each fetch NEVER raises: a failure → None → flow_no_data
(spec §5.A). Parsing is pure and column-name-tolerant: an unexpected shape →
empty → N/A, NEVER a fabricated value.

Flow units are PERCENT-POINTS (D3): akshare parses the EastMoney 净占比 column via
pd.to_numeric with NO /100, so 12.34 means 12.34%. NO /100 here. CN endpoint
stays DIRECT (no IRC_HTTPS_PROXY) per the project http-proxy rule (ADR 0017).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

_log = logging.getLogger(__name__)

# A FlowSeries is parsed rows, NEVER a DataFrame, so the on-disk form is
# byte-stable: (date_iso, main_net_pct) in percent-points, sorted ascending.
FlowSeries = tuple[tuple[str, float], ...]

_DATE_COL = "日期"
_NET_PCT_COL = "主力净流入-净占比"


def _coerce(value: object) -> float | None:
    """Pure: numeric value or None for non-numeric / NaN. NO /100 (percent-points)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def parse_main_net_pct(df: pd.DataFrame | None) -> FlowSeries:
    """Pure: extract (date_iso, 主力净流入-净占比) rows, sorted ascending by date,
    percent-point units. Rows with a non-numeric/NaN 净占比 are dropped. Unexpected
    shape (missing columns / empty / None) → empty tuple (→ N/A, never fabricated)."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return ()
    if _DATE_COL not in df.columns or _NET_PCT_COL not in df.columns:
        return ()
    rows: list[tuple[str, float]] = []
    for _, row in df.iterrows():
        pct = _coerce(row[_NET_PCT_COL])
        if pct is None:
            continue
        rows.append((str(row[_DATE_COL]).strip(), pct))
    return tuple(sorted(rows, key=lambda r: r[0]))


_ROUND_DP = 4


def _rows_for(series: FlowSeries) -> list[dict]:
    """Sorted ascending by date, main_net_pct rounded to 4dp (byte-stable)."""
    return [
        {"date": d, "main_net_pct": round(pct, _ROUND_DP)}
        for d, pct in sorted(series, key=lambda r: r[0])
    ]


def _cache_payload(by_symbol: dict[str, FlowSeries | None]) -> dict[str, dict]:
    """Pure: symbol→series map → deterministic cache dict. None → status:miss
    (records a confirmed fetch failure so re-runs don't re-hit a dead symbol).
    Symbols sorted; rows sorted+rounded."""
    out: dict[str, dict] = {}
    for symbol in sorted(by_symbol):
        series = by_symbol[symbol]
        if series is None:
            out[symbol] = {"status": "miss", "rows": []}
        else:
            out[symbol] = {"status": "ok", "rows": _rows_for(series)}
    return out


def _load_cache_payload(payload: dict[str, dict]) -> dict[str, FlowSeries | None]:
    """Pure: cache dict → symbol→(series|None) map. ok→FlowSeries, miss→None."""
    out: dict[str, FlowSeries | None] = {}
    for symbol, entry in payload.items():
        if entry.get("status") != "ok":
            out[symbol] = None
            continue
        out[symbol] = tuple(
            (str(r["date"]), float(r["main_net_pct"])) for r in entry.get("rows", [])
        )
    return out


def _market_of(symbol: str) -> str | None:
    """Pure: A-share market for ak.stock_individual_fund_flow. 6*→sh, 0*/3*→sz,
    8*/4*→bj. A non-6-digit symbol or any other prefix → None (HK/US QDII lines
    are not A-shares → never fetched → uncovered)."""
    s = str(symbol).strip()
    if len(s) != 6 or not s.isdigit():
        return None
    head = s[0]
    if head == "6":
        return "sh"
    if head in ("0", "3"):
        return "sz"
    if head in ("8", "4"):
        return "bj"
    return None


_PACING_SECONDS = 0.3  # light pacing between live CN calls (ADR 0014 rate-limit posture)


def _cache_path(cache_dir: Path, today: str) -> Path:
    return cache_dir / f"{today}.json"


def _read_cache(cache_dir: Path, today: str) -> dict[str, FlowSeries | None]:
    path = _cache_path(cache_dir, today)
    if not path.is_file():
        return {}
    try:
        return _load_cache_payload(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
        _log.warning("flow_fetch: unreadable cache %s; refetching", path, exc_info=True)
        return {}


def _write_cache(cache_dir: Path, today: str, by_symbol: dict[str, FlowSeries | None]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = _cache_payload(by_symbol)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    import os
    tmp = _cache_path(cache_dir, today).with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _cache_path(cache_dir, today))


def _fetch_one(symbol: str, fetch, *, sleep) -> FlowSeries | None:
    """EDGE: one symbol → FlowSeries or None. NEVER raises. Non-A-share → None
    (skipped, never fetched). CN endpoint DIRECT."""
    market = _market_of(symbol)
    if market is None:
        return None
    try:
        df = fetch(stock=symbol, market=market)
    except Exception:  # noqa: BLE001 — degrade to None (flow_no_data), never crash
        _log.warning("flow_fetch: stock_individual_fund_flow failed for %s", symbol,
                     exc_info=True)
        return None
    sleep(_PACING_SECONDS)
    return parse_main_net_pct(df)


def fetch_flow_series(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
) -> dict[str, FlowSeries | None]:
    """EDGE: dedup symbols → cache-first per-day fetch → byte-stable cache write.
    Idempotent within a day (--resume / drilldown re-render never re-fetch).
    `fetch` is injectable for tests; the default lazy-imports akshare (house
    pattern). ~15-25 sequential CN calls/run, free endpoint."""
    if fetch is None:
        import akshare as ak  # local import — house pattern, no module-top akshare
        fetch = ak.stock_individual_fund_flow
    cached = _read_cache(cache_dir, today)
    out: dict[str, FlowSeries | None] = {}
    dirty = False
    for symbol in dict.fromkeys(symbols):  # dedup, preserve order
        if symbol in cached:
            out[symbol] = cached[symbol]
            continue
        out[symbol] = _fetch_one(symbol, fetch, sleep=sleep)
        dirty = True
    if dirty:
        _write_cache(cache_dir, today, {**cached, **out})
    return out
