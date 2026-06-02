from __future__ import annotations

import dataclasses
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from irc.fundamentals.akshare_fundamentals import _ak_call
from irc.io_utils import atomic_write_text
from irc.narrative.schemas import Holding

_log = logging.getLogger(__name__)

_TOP_N = 10
_NEEDED = {"股票代码", "股票名称", "占净值比例"}
_INDUSTRY_COLS = ("申万一级行业", "所属行业")


def _current_year() -> str:
    return str(datetime.now(timezone.utc).year)


def _industry(row: pd.Series) -> str:
    for col in _INDUSTRY_COLS:
        if col in row.index and pd.notna(row[col]):
            return str(row[col])
    return ""


def _to_holding(row: pd.Series) -> Holding:
    try:
        weight = float(row["占净值比例"])
    except (TypeError, ValueError):
        weight = 0.0
    if math.isnan(weight) or math.isinf(weight):
        weight = 0.0
    return Holding(
        symbol=str(row["股票代码"]).strip(),
        name_cn=str(row["股票名称"]).strip(),
        weight_pct=weight,
        sw_industry=_industry(row),
    )


def _parse(df: pd.DataFrame) -> tuple[Holding, ...]:
    if not isinstance(df, pd.DataFrame) or df.empty or not _NEEDED.issubset(df.columns):
        return ()
    # Sort descending so highest weight comes first, then dedupe by symbol.
    ranked = df.sort_values("占净值比例", ascending=False)
    seen: set[str] = set()
    holdings: list[Holding] = []
    for _i, row in ranked.iterrows():
        h = _to_holding(row)
        if h.symbol in seen:
            continue
        seen.add(h.symbol)
        holdings.append(h)
        if len(holdings) == _TOP_N:
            break
    return tuple(holdings)


def _read_cache(path: Path) -> tuple[Holding, ...] | None:
    if not path.exists():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("holdings cache unreadable: %s — %s", path, exc)
        return None
    return tuple(Holding(**h) for h in body.get("holdings", []))


def _write_cache(path: Path, holdings: tuple[Holding, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"holdings": [dataclasses.asdict(h) for h in holdings]}
    atomic_write_text(path, json.dumps(doc, ensure_ascii=False, indent=2))


def fetch_top_holdings(fund_id: str, *, cache_dir: Path) -> tuple[Holding, ...]:
    """I/O edge: top-10 disclosed holdings for a fund (AkShare, cached). Never raises."""
    cache_path = cache_dir / f"{fund_id}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached
    try:
        df = _ak_call("fund_portfolio_hold_em", symbol=fund_id, date=_current_year())
    except Exception as exc:
        _log.warning("fetch_top_holdings failed for %s: %s", fund_id, exc)
        return ()
    holdings = _parse(df)
    _write_cache(cache_path, holdings)
    return holdings
