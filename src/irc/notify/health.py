"""PURE data-health digest builders. No I/O — the notify edge reads the
artifact files and passes already-parsed dicts. Mirrors classify.py
(CONTEXT.md "Data-health digest" / ADR 0016 amendment).

Every builder is TOTAL: a missing/corrupt input dict yields a single `warn`
`health_unknown` item, never an exception (degrade-never-crash, ADR 0016 AC8).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Level = Literal["info", "warn"]

_COVERAGE_FLOOR = 0.80
_MACRO_MAX_AGE_DAYS = 7
_MAX_SIGNAL_IDS = 3


@dataclass(frozen=True)
class HealthItem:
    code: str
    level: Level
    text: str


@dataclass(frozen=True)
class HealthDigest:
    items: tuple[HealthItem, ...]

    @property
    def has_warnings(self) -> bool:
        return any(item.level == "warn" for item in self.items)


_UNKNOWN = HealthDigest(
    (HealthItem("health_unknown", "warn", "health unknown — 健康检查数据缺失/损坏"),)
)  # text carries the literal "health unknown" (AC5) + the CN gloss


def monitor_health(
    trace: dict, flow_store: dict, trading_days: tuple[date, ...]
) -> HealthDigest:
    """Board-PE freshness + flow recency/coverage + per-fund signal status."""
    if not trace or "board_pe_freshness" not in trace:
        return _UNKNOWN
    items = (
        _board_pe_item(trace["board_pe_freshness"])
        + _flow_items(flow_store, trading_days)
        + _signal_items(trace.get("funds", {}))
    )
    return HealthDigest(items)


def _board_pe_item(bpf: dict) -> tuple[HealthItem, ...]:
    state = bpf.get("state")
    if state == "DARK":
        return (HealthItem("board_pe_dark", "warn", "板块PE: DARK ≥4td — 价值陷阱检测不可用"),)
    if state == "STALE":
        return (HealthItem("board_pe_stale", "info",
                           f"板块PE: STALE-{bpf.get('age_td')} ({bpf.get('as_of')})"),)
    return ()


def _newest_by_symbol(flow_store: dict) -> dict[str, str]:
    return {sym: max(row[0] for row in rows) for sym, rows in flow_store.items() if rows}


def _flow_items(flow_store: dict, trading_days: tuple[date, ...]) -> tuple[HealthItem, ...]:
    newest = _newest_by_symbol(flow_store)
    if not newest:
        return ()
    run_newest = max(newest.values())
    total = len(newest)
    at_newest = sum(1 for d in newest.values() if d == run_newest)
    head = f"资金流: 最新 {run_newest} · 覆盖 {at_newest}/{total}"
    stale = _stale_symbols(newest, trading_days)
    if stale and at_newest < total:  # some symbols lag the pack — a real per-symbol outlier,
        # not just every symbol uniformly behind (that's the run-level case below, G-Q5→B)
        oldest = min(newest[sym] for sym in stale)
        return (HealthItem("flow_symbol_stale", "warn",
                           f"{head} · {len(stale)} 只滞后>3td(最旧 {oldest})"),)
    if _run_level_stale(run_newest, at_newest, total, trading_days):
        return (HealthItem("flow_stale", "warn", head),)
    return ()


def _stale_symbols(newest: dict[str, str], trading_days: tuple[date, ...]) -> tuple[str, ...]:
    if len(trading_days) < 4:
        return ()
    cutoff = trading_days[-4].isoformat()  # >3 trading days old ⇒ older than the 4th-recent session
    return tuple(sym for sym, d in newest.items() if d < cutoff)


def _run_level_stale(
    run_newest: str, at_newest: int, total: int, trading_days: tuple[date, ...]
) -> bool:
    lagging = len(trading_days) >= 2 and run_newest < trading_days[-2].isoformat()
    return lagging or (at_newest / total) < _COVERAGE_FLOOR


def _signal_items(funds: dict) -> tuple[HealthItem, ...]:
    if not funds:
        return ()
    bad = tuple(
        fid for fid, rec in funds.items()
        if rec.get("signal", {}).get("status") != "ok"
        or rec.get("published_state") == "NO_CALL"
    )
    if not bad:
        return ()
    listed = ", ".join(bad[:_MAX_SIGNAL_IDS])
    return (HealthItem("signal_not_ok", "warn",
                       f"信号: {len(bad)}/{len(funds)} 非 ok (NO_CALL: {listed})"),)
