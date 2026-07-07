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
    flow = _read_json(root / "data" / "monitor" / "fund_flow_series.json") or {}
    tdays = recent_trading_days(today, holidays, _TRADING_DAY_LOOKBACK)
    return monitor_health(trace, flow, tdays)


def read_weekly_health(root: Path, today: date) -> HealthDigest:
    gold = _read_json(root / "outputs" / today.isoformat() / "gold_regime.json") or {}
    return weekly_health(gold, today)


def _recent_rotation_statuses(root: Path, today: date) -> tuple[str, ...]:
    outputs = root / "outputs"
    if not outputs.exists():
        return ()
    dated: list[tuple[str, str]] = []
    for radar in outputs.glob("*/rotation/rotation_radar.json"):
        day = radar.parent.parent.name
        if day > today.isoformat():
            continue
        data = _read_json(radar) or {}
        dated.append((day, str(data.get("data_status", "unknown"))))
    dated.sort(key=lambda pair: pair[0])
    return tuple(status for _, status in dated[-_RECENT_RADAR_DAYS:])


def read_flow_capture(root: Path, today: date) -> tuple[HealthDigest, bool]:
    """Return (digest, force_notify). abstain→ok recovery ⇒ info digest + force."""
    radar_path = root / "outputs" / today.isoformat() / "rotation" / "rotation_radar.json"
    radar = _read_json(radar_path) or {}
    recent = _recent_rotation_statuses(root, today)
    recovery = detect_rotation_recovery(recent, len(radar.get("board_states", [])))
    if recovery is not None:
        return HealthDigest((HealthItem("rotation_recovered", "info", recovery),)), True
    return rotation_health(radar, recent), False
