"""EDGE: read on-disk artifacts and hand parsed dicts to the pure
`irc.notify.health` builders. All filesystem effects for the data-health
digest live here; the builders stay pure (ADR 0016 amendment)."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from irc.notify.calendar import recent_trading_days
from irc.notify.health import (
    HEALTH_UNKNOWN,
    HealthDigest,
    HealthItem,
    detect_rotation_recovery,
    monitor_health,
    rotation_health,
    weekly_health,
)

_log = logging.getLogger(__name__)
_RECENT_RADAR_DAYS = 5
_TRADING_DAY_LOOKBACK = 5
_FLOW_UNREADABLE_ITEM = HealthItem(
    "health_unknown", "warn",
    "health unknown — 资金流数据缺失/损坏 (fund_flow_series.json 不可读)",
)


def _safe_health(builder, *args) -> HealthDigest:
    """Edge-level safety net (P0-1b): ANY exception from a pure health
    builder — including a future shape bug the isinstance guards in
    `irc.notify.health` don't yet cover — degrades to health_unknown instead
    of crashing the notifier (ADR 0016 AC8)."""
    try:
        return builder(*args)
    except Exception:  # noqa: BLE001 — degrade-never-crash
        _log.warning(
            "data-health: %s raised — degrading to health_unknown",
            getattr(builder, "__name__", repr(builder)), exc_info=True,
        )
        return HEALTH_UNKNOWN


def _read_json(path: Path) -> dict | None:
    """Best-effort JSON read. Missing/unparseable/non-object → None (never raises)."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        _log.warning("data-health: could not read %s", path.name)
        return None
    return data if isinstance(data, dict) else None


def read_monitor_health(root: Path, today: date, holidays: set[date]) -> HealthDigest:
    out = root / "outputs" / today.isoformat()
    trace = _read_json(out / "monitor" / "eval_trace.json") or {}
    flow = _read_json(root / "data" / "monitor" / "fund_flow_series.json")
    tdays = recent_trading_days(today, holidays, _TRADING_DAY_LOOKBACK)
    digest = _safe_health(monitor_health, trace, flow or {}, tdays)
    return _flag_flow_unreadable(digest) if flow is None else digest


def _flag_flow_unreadable(digest: HealthDigest) -> HealthDigest:
    """P0-2: an absent/corrupt fund_flow_series.json must never silently
    render as clean — append a health_unknown item so has_warnings is always
    True, even when every other leg of the digest is fine."""
    return HealthDigest(digest.items + (_FLOW_UNREADABLE_ITEM,))


def read_weekly_health(root: Path, today: date) -> HealthDigest:
    gold = _read_json(root / "outputs" / today.isoformat() / "gold_regime.json") or {}
    return _safe_health(weekly_health, gold, today)


def _recent_rotation_statuses(root: Path, today: date) -> tuple[str, ...]:
    """A day whose rotation_radar.json exists but fails to parse is DROPPED
    (absent evidence) rather than labelled "unknown" (P0-3): an "unknown"
    label is neither degraded nor "ok" to `_consecutive_degraded`'s reversed
    scan, which stops the scan early and can suppress a real recovery."""
    outputs = root / "outputs"
    if not outputs.exists():
        return ()
    dated: list[tuple[str, str]] = []
    for radar in outputs.glob("*/rotation/rotation_radar.json"):
        day = radar.parent.parent.name
        if day > today.isoformat():
            continue
        data = _read_json(radar)
        if data is None:
            _log.warning("data-health: dropping unreadable rotation_radar.json for day %s", day)
            continue
        dated.append((day, str(data.get("data_status", "unknown"))))
    dated.sort(key=lambda pair: pair[0])
    return tuple(status for _, status in dated[-_RECENT_RADAR_DAYS:])


def _compute_flow_capture_health(
    radar: dict, recent: tuple[str, ...], radar_exists: bool
) -> tuple[HealthDigest, bool]:
    """radar_exists gates recovery detection — a crashed run (today's radar
    missing) must never inherit yesterday's recovery notice (P1-4): the
    today-last invariant `detect_rotation_recovery` relies on has to be real."""
    if radar_exists:
        recovery = detect_rotation_recovery(recent, len(radar.get("board_states", [])))
        if recovery is not None:
            return HealthDigest((HealthItem("rotation_recovered", "info", recovery),)), True
    return rotation_health(radar, recent), False


def read_flow_capture(root: Path, today: date) -> tuple[HealthDigest, bool]:
    """Return (digest, force_notify). abstain→ok recovery ⇒ info digest + force."""
    radar_path = root / "outputs" / today.isoformat() / "rotation" / "rotation_radar.json"
    radar_exists = radar_path.exists()
    radar = _read_json(radar_path) or {}
    recent = _recent_rotation_statuses(root, today)
    try:
        return _compute_flow_capture_health(radar, recent, radar_exists)
    except Exception:  # noqa: BLE001 — degrade-never-crash (ADR 0016 AC8)
        _log.warning("data-health: flow-capture health build raised", exc_info=True)
        return HEALTH_UNKNOWN, False
