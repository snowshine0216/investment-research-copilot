"""PURE data-health digest builders. No file/clock/env access — the notify edge
reads artifacts + clock and passes dicts + dates here. Mirrors classify.py.

Every builder is TOTAL: corrupt/malformed input yields a single `warn`
`health_unknown` item, never an exception (degrade-never-crash, ADR 0016 AC8).
Missing artifact files are the notify_cmd edge's responsibility (spec §3.3);
builders here always receive parsed values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from irc.notify.calendar import previous_trading_day, trading_day_age

Level = Literal["info", "warn"]

_COVERAGE_FLOOR = 0.80
_STALE_TD_LIMIT = 3
_MACRO_AGE_LIMIT_DAYS = 7
_MAX_SIGNAL_IDS = 5
_UNKNOWN_TEXT = "数据健康未知 (health unknown)"


@dataclass(frozen=True)
class HealthItem:
    code: str
    level: Level
    text: str


@dataclass(frozen=True)
class HealthDigest:
    items: tuple[HealthItem, ...] = ()

    @property
    def has_warnings(self) -> bool:
        return any(i.level == "warn" for i in self.items)


def health_unknown() -> HealthDigest:
    return HealthDigest((HealthItem("health_unknown", "warn", _UNKNOWN_TEXT),))


def _md(iso: str) -> str:
    """`2026-07-06` -> `07-06` (MM-DD render form used across the digest)."""
    return iso[5:]


def monitor_health(
    trace: dict, flow_store: dict, *, today: date, holidays: frozenset[date]
) -> HealthDigest:
    """Monitor (12:15) digest: board-PE + flow-store recency + per-fund signal."""
    try:
        items = (
            *_board_pe_items(trace),
            *_flow_items(flow_store, today=today, holidays=holidays),
            *_signal_items(trace),
        )
        return HealthDigest(items)
    except Exception:  # noqa: BLE001 — total function (ADR 0016 AC8)
        return health_unknown()


def _board_pe_items(trace: dict) -> tuple[HealthItem, ...]:
    fresh = (trace or {}).get("board_pe_freshness") or {}
    state = fresh.get("state")
    if state == "DARK":
        return (HealthItem("board_pe_dark", "warn",
                           "板块PE: DARK ≥4td — 价值陷阱检测不可用"),)
    if state == "STALE":
        return (HealthItem("board_pe_stale", "info",
                           f"板块PE: STALE-{fresh.get('age_td')} ({_md(fresh.get('as_of'))})"),)
    return ()


def _newest_dates(flow_store: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for sym, rows in (flow_store or {}).items():
        dates = [r[0] for r in rows if isinstance(r, (list, tuple)) and r]
        out[sym] = max(dates) if dates else None
    return out


def _flow_items(
    flow_store: dict, *, today: date, holidays: frozenset[date]
) -> tuple[HealthItem, ...]:
    newest = _newest_dates(flow_store)
    if not newest:
        return ()
    total = len(newest)
    overall = max(v for v in newest.values() if v)
    at_newest = sum(1 for v in newest.values() if v == overall)
    items: list[HealthItem] = []
    lag = trading_day_age(date.fromisoformat(overall), today, holidays)
    if date.fromisoformat(overall) < previous_trading_day(today, holidays) or (
        at_newest < total * _COVERAGE_FLOOR
    ):
        items.append(HealthItem("flow_stale", "warn",
                                f"资金流: 最新 {_md(overall)} (滞后 {lag}td), 覆盖 {at_newest}/{total}"))
    stale = [(s, v) for s, v in newest.items()
             if v and trading_day_age(date.fromisoformat(v), today, holidays) > _STALE_TD_LIMIT]
    if stale:
        oldest = min(v for _, v in stale)
        items.append(HealthItem("flow_symbol_stale", "warn",
                                f"资金流: 最新 {_md(overall)} · 覆盖 {at_newest}/{total} · "
                                f"{len(stale)} 只滞后>3td(最旧 {_md(oldest)})"))
    return tuple(items)


def _signal_items(trace: dict) -> tuple[HealthItem, ...]:
    funds = (trace or {}).get("funds") or {}
    total = len(funds)
    non_ok = [fid for fid, f in funds.items()
              if ((f or {}).get("signal") or {}).get("status", "ok") != "ok"]
    if not non_ok:
        return ()
    listed = ", ".join(sorted(non_ok)[:_MAX_SIGNAL_IDS])
    return (HealthItem("signal_not_ok", "warn",
                       f"信号: {len(non_ok)}/{total} 非 ok (NO_CALL: {listed})"),)


def rotation_health(
    radar: dict,
    recent_statuses: tuple[str, ...],
    *,
    flow_capture_cov: tuple[int, int] | None = None,
) -> HealthDigest:
    """Flow-capture (15:45) digest: rotation status + flow-capture coverage."""
    try:
        items: list[HealthItem] = []
        status = (radar or {}).get("data_status")
        if status == "abstain":
            items.append(HealthItem("rotation_abstain", "warn",
                                    f"轮动雷达: 弃权 (连续第 {_abstain_streak(recent_statuses)} 日)"))
        elif isinstance(status, str) and status.startswith("degraded_"):
            items.append(HealthItem("rotation_degraded", "warn", f"轮动雷达: {status}"))
        if flow_capture_cov is not None:
            at, total = flow_capture_cov
            if total and at < total * _COVERAGE_FLOOR:
                items.append(HealthItem("flow_capture_coverage", "warn", f"flow-capture: {at}/{total}"))
        return HealthDigest(tuple(items))
    except Exception:  # noqa: BLE001 — total function (ADR 0016 AC8)
        return health_unknown()


def _abstain_streak(recent_statuses: tuple[str, ...]) -> int:
    streak = 0
    for s in recent_statuses:
        if s == "abstain":
            streak += 1
        else:
            break
    return streak


def weekly_health(gold_regime: dict, *, today: date) -> HealthDigest:
    """Weekly (Sat 09:00) digest: macro-driver age + unavailable drivers."""
    try:
        items: list[HealthItem] = []
        for snap in (gold_regime or {}).get("macro_snapshots") or []:
            iso = snap.get("date")
            if not iso:
                continue
            age = (today - date.fromisoformat(iso)).days
            if age > _MACRO_AGE_LIMIT_DAYS:
                items.append(HealthItem("macro_driver_stale", "warn",
                                        f"宏观驱动: {snap.get('series_id')} 滞后 {age}d ({_md(iso)})"))
        for drv in (gold_regime or {}).get("drivers_unavailable") or []:
            items.append(HealthItem("macro_driver_unavailable", "info", f"缺失驱动: {drv}"))
        return HealthDigest(tuple(items))
    except Exception:  # noqa: BLE001 — total function (ADR 0016 AC8)
        return health_unknown()
