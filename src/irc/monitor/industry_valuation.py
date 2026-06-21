"""EDGE + pure parse: monitor industry valuation leg via AkShare (ADR 0020).

Two cached/day reads, mirroring flow_fetch.py's contract (never raises, parsed
rows, per-day JSON cache, DIRECT CN endpoint, light pacing):

- `stock_board_industry_name_em` — ONE market-wide call → 东财 industry → avg PE.
- `stock_individual_info_em(symbol)` — per-symbol → the symbol's 东财 industry
  (~15-25 deduped cached calls/run, same volume + contract as flow_fetch).

Industry-average PE is from a single 市盈率 column (cap-weighting unverified at
the source; see ADR 0020 denominator-robustness risk). NON-positive / NaN PE →
dropped (→ industry_no_data per-stock). No DataFrame on disk; the cache stores
parsed primitives so the on-disk form is byte-stable. CN endpoints stay DIRECT
(no IRC_HTTPS_PROXY) per ADR 0017.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

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


_PACING_SECONDS = 0.3  # light pacing between live CN calls (ADR 0014 posture)


def _cache_path(cache_dir: Path, today: str) -> Path:
    return cache_dir / f"{today}.json"


def _write_json(cache_dir: Path, today: str, payload: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = _cache_path(cache_dir, today).with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _cache_path(cache_dir, today))


def _read_json(cache_dir: Path, today: str) -> dict | None:
    path = _cache_path(cache_dir, today)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log.warning("industry_valuation: unreadable cache %s; refetching", path,
                     exc_info=True)
        return None


def fetch_industry_pe(
    *, cache_dir: Path, today: str, fetch=None, sleep=time.sleep,
) -> dict[str, float]:
    """EDGE: ONE market-wide stock_board_industry_name_em call/day, cached.
    NEVER raises — any failure → {} (→ industry leg N/A). fetch injectable for
    tests; default lazy-imports akshare (house pattern). CN endpoint DIRECT."""
    cached = _read_json(cache_dir, today)
    if cached is not None:
        return {str(k): float(v) for k, v in cached.items()}
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_board_industry_name_em
    try:
        df = fetch()
    except Exception:  # noqa: BLE001 — degrade to {}, never crash the brief
        _log.warning("industry_valuation: stock_board_industry_name_em failed",
                     exc_info=True)
        return {}
    sleep(_PACING_SECONDS)
    parsed = parse_industry_pe(df)
    _write_json(cache_dir, today, parsed)
    return parsed


def _industry_cache_payload(by_symbol: dict[str, str | None]) -> dict[str, dict]:
    """Pure: symbol→industry map → deterministic cache dict (sorted symbols).
    None → status:miss (records a confirmed failure so re-runs skip dead symbols)."""
    return {
        symbol: ({"status": "ok", "industry": by_symbol[symbol]}
                 if by_symbol[symbol] is not None
                 else {"status": "miss", "industry": None})
        for symbol in sorted(by_symbol)
    }


def _load_industry_cache(payload: dict[str, dict]) -> dict[str, str | None]:
    """Pure: cache dict → symbol→(industry|None) map."""
    out: dict[str, str | None] = {}
    for symbol, entry in payload.items():
        out[symbol] = entry.get("industry") if entry.get("status") == "ok" else None
    return out


def _read_industry_cache(cache_dir: Path, today: str) -> dict[str, str | None]:
    payload = _read_json(cache_dir, today)
    return _load_industry_cache(payload) if payload else {}


def _fetch_one_industry(symbol: str, fetch, *, sleep) -> str | None:
    """EDGE: one symbol → industry or None. NEVER raises. CN endpoint DIRECT."""
    try:
        df = fetch(symbol=symbol)
    except Exception:  # noqa: BLE001 — degrade to None (industry_no_data)
        _log.warning("industry_valuation: stock_individual_info_em failed for %s",
                     symbol, exc_info=True)
        return None
    sleep(_PACING_SECONDS)
    return parse_stock_industry(df)


def fetch_stock_industry_map(
    symbols: tuple[str, ...], *, cache_dir: Path, today: str,
    fetch=None, sleep=time.sleep,
) -> dict[str, str | None]:
    """EDGE: dedup symbols → cache-first per-day per-symbol fetch → byte-stable
    cache write (ok/miss). Idempotent within a day. Same contract + volume as
    flow_fetch.fetch_flow_series. fetch injectable; default lazy-imports akshare."""
    if fetch is None:
        import akshare as ak  # local import — house pattern
        fetch = ak.stock_individual_info_em
    cached = _read_industry_cache(cache_dir, today)
    out: dict[str, str | None] = {}
    dirty = False
    for symbol in dict.fromkeys(symbols):  # dedup, preserve order
        if symbol in cached:
            out[symbol] = cached[symbol]
            continue
        out[symbol] = _fetch_one_industry(symbol, fetch, sleep=sleep)
        dirty = True
    if dirty:
        _write_json(cache_dir, today, _industry_cache_payload({**cached, **out}))
    return out
