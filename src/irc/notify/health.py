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
HEALTH_UNKNOWN = _UNKNOWN  # public alias — the notify_health edge net reuses this digest


def monitor_health(
    trace: dict, flow_store: dict, trading_days: tuple[date, ...]
) -> HealthDigest:
    """Board-PE freshness + flow recency/coverage + per-fund signal status."""
    if not _monitor_shape_ok(trace):
        return _UNKNOWN
    funds = trace.get("funds") or {}
    if not _funds_shape_ok(funds):
        return _UNKNOWN
    items = (
        _board_pe_item(trace["board_pe_freshness"])
        + _flow_items(flow_store if isinstance(flow_store, dict) else {}, trading_days)
        + _signal_items(funds)
    )
    return HealthDigest(items)


def _monitor_shape_ok(trace: object) -> bool:
    """isinstance guard — a missing/None/wrong-type board_pe_freshness must
    degrade to health_unknown rather than crash `_board_pe_item` (P0-1)."""
    return (
        isinstance(trace, dict)
        and "board_pe_freshness" in trace
        and isinstance(trace["board_pe_freshness"], dict)
    )


def _funds_shape_ok(funds: object) -> bool:
    """isinstance guard — funds must be a dict of dicts; a non-dict container
    or a non-dict per-fund record both crashed `_signal_items` (P0-1)."""
    return isinstance(funds, dict) and all(isinstance(rec, dict) for rec in funds.values())


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


def rotation_health(radar: dict, recent_statuses: tuple[str, ...]) -> HealthDigest:
    """Rotation abstain/degraded → warn; ok → empty; missing → unknown."""
    if not radar or "data_status" not in radar:
        return _UNKNOWN
    status = radar["data_status"]
    if status == "abstain":
        consec = _consecutive_degraded(recent_statuses)
        return HealthDigest((HealthItem("rotation_abstain", "warn",
                             f"轮动雷达: 弃权 (连续第 {consec} 日)"),))
    if isinstance(status, str) and status.startswith("degraded_"):
        return HealthDigest((HealthItem("rotation_degraded", "warn",
                             f"轮动雷达: {status}"),))
    return HealthDigest(())


def _is_degraded(status: object) -> bool:
    return status == "abstain" or (isinstance(status, str) and status.startswith("degraded_"))


def _consecutive_degraded(recent_statuses: tuple[str, ...]) -> int:
    count = 0
    for status in reversed(recent_statuses):
        if not _is_degraded(status):
            break
        count += 1
    return count


def detect_rotation_recovery(
    recent_statuses: tuple[str, ...], board_count: int
) -> str | None:
    """Body for the one-time abstain→ok recovery notice, else None."""
    if len(recent_statuses) < 2 or recent_statuses[-1] != "ok":
        return None
    prior_run = _consecutive_degraded(recent_statuses[:-1])
    if prior_run == 0:
        return None
    return f"轮动雷达恢复 ok ({board_count} boards) — 此前弃权 {prior_run} 日"


def weekly_health(gold_regime: dict, today: date) -> HealthDigest:
    """Macro-driver age (>7 calendar days ⇒ warn) + drivers_unavailable (info)."""
    if not _weekly_shape_ok(gold_regime):
        return _UNKNOWN
    items = _macro_items(gold_regime.get("macro_snapshots", []), today)
    items += _unavailable_items(gold_regime.get("drivers_unavailable", []))
    return HealthDigest(items)


def _weekly_shape_ok(gold_regime: object) -> bool:
    """isinstance guard — `dict.get(key, default)` only applies the default
    when the key is ABSENT, not when its value is JSON null, so a null
    macro_snapshots/drivers_unavailable must be caught explicitly here rather
    than crash `_macro_items`/`_unavailable_items` downstream (P0-1)."""
    if not isinstance(gold_regime, dict) or not gold_regime:
        return False
    return (
        isinstance(gold_regime.get("macro_snapshots", []), list)
        and isinstance(gold_regime.get("drivers_unavailable", []), list)
    )


def _macro_items(snapshots: list, today: date) -> tuple[HealthItem, ...]:
    out: list[HealthItem] = []
    for snap in snapshots:
        if not isinstance(snap, dict):
            continue
        age = _driver_age(snap.get("date"), today)
        if age is not None and age > _MACRO_MAX_AGE_DAYS:
            out.append(HealthItem("macro_driver_stale", "warn",
                       f"宏观驱动: {snap.get('series_id')} 滞后 {age}d ({snap.get('date')})"))
    return tuple(out)


def _driver_age(raw: object, today: date) -> int | None:
    try:
        return (today - date.fromisoformat(str(raw))).days
    except (TypeError, ValueError):
        return None


def _unavailable_items(names: list) -> tuple[HealthItem, ...]:
    return tuple(
        HealthItem("driver_unavailable", "info", f"缺失驱动: {name}") for name in names
    )
