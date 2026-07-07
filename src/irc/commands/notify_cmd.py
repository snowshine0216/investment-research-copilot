"""EDGE: read today's artifacts → RunOutcome → classify → dispatch.

All effects live here: `_china_today` (clock), `_build_outcome`/`_load_holidays`
(filesystem), `_send_macos` (osascript via subprocess), `_send_feishu` (httpx
POST). The pure logic is imported from `irc.notify`. A transport failure logs
and sets a non-zero return WITHOUT raising — a broken notifier must never mask
the underlying run result (ADR 0016 / AC8).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from irc.notify.classify import classify_run_outcome
from irc.notify.health import (
    HealthDigest,
    health_unknown,
    monitor_health,
    rotation_health,
    weekly_health,
)
from irc.notify.message import format_feishu, format_macos
from irc.notify.types import NotificationDecision, RunOutcome

_log = logging.getLogger(__name__)
# httpx logs the full request URL (including secret token path) at INFO level;
# httpcore only uses DEBUG. Silence httpx INFO so the Feishu webhook token never
# reaches the root handler → stderr → launchd StandardErrorPath log files.
logging.getLogger("httpx").setLevel(logging.WARNING)
_TRUE = {"1", "true", "yes", "on"}
_FEISHU_ENV = "IRC_FEISHU_WEBHOOK_URL"
_CLEAN_ENV = "IRC_NOTIFY_ON_CLEAN"


def _china_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _load_holidays(root: Path) -> set[date]:
    """Read config/cn_market_holidays.yaml (flat YYYY-MM-DD list). Absent ⇒ {}.

    Malformed YAML or invalid date values degrade gracefully: log a warning and
    return an empty set so classification still proceeds (P0-4).
    """
    path = root / "config" / "cn_market_holidays.yaml"
    if not path.exists():
        return set()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        return {date.fromisoformat(str(item)) for item in raw}
    except (yaml.YAMLError, ValueError) as exc:
        _log.warning("could not load holiday YAML — weekend-only skip in effect: %s", exc)
        return set()


def _build_outcome(root: Path, *, run_kind: str, last_exit_code: int) -> RunOutcome:
    """Gather today's on-disk artifacts into a frozen RunOutcome (no fallback)."""
    out_dir = root / "outputs" / _china_today().isoformat()
    if run_kind == "monitor":
        # monitor.json is the LAST of _write_outputs' five atomic writes, so its
        # presence is the only artifact that proves the full set was written. A
        # crash after report.html but before monitor.json leaves a partial set;
        # keying on report.html would mis-report that as success.
        sentinel = out_dir / "monitor" / "monitor.json"
        return RunOutcome(
            run_kind=run_kind,
            last_exit_code=last_exit_code,
            today_dir_exists=sentinel.exists(),  # success iff monitor.json written
            pipeline_halted=False,
            stale_ingest=False,
            actionable_buy_count=0,
            trim_count=0,
            exit_count=0,
            review_count=0,
            health=_build_monitor_health(root, out_dir),
        )
    if run_kind == "flow-capture":
        sentinel = out_dir / "rotation" / "rotation_radar.json"
        digest, recovery = _build_flow_capture_health(root, out_dir)
        return RunOutcome(
            run_kind=run_kind,
            last_exit_code=last_exit_code,
            today_dir_exists=sentinel.exists(),  # crash iff rotation_radar.json absent
            pipeline_halted=False,
            stale_ingest=False,
            actionable_buy_count=0,
            trim_count=0,
            exit_count=0,
            review_count=0,
            health=digest,
            recovery_notice=recovery,
        )
    if not out_dir.exists():
        return RunOutcome(
            run_kind=run_kind,
            last_exit_code=last_exit_code,
            today_dir_exists=False,
            pipeline_halted=False,
            stale_ingest=False,
            actionable_buy_count=0,
            trim_count=0,
            exit_count=0,
            review_count=0,
        )
    summary = _read_summary(out_dir / "decision_report.json")
    unreadable = summary is None
    safe = summary if summary is not None else {}
    return RunOutcome(
        run_kind=run_kind,
        last_exit_code=last_exit_code,
        today_dir_exists=True,
        pipeline_halted=(out_dir / "PIPELINE_HALTED.md").exists(),
        stale_ingest=(out_dir / "STALE_INGEST.md").exists(),
        actionable_buy_count=int(safe.get("actionable_buy_count", 0) or 0),
        trim_count=safe.get("trim_count"),
        exit_count=safe.get("exit_count"),
        review_count=safe.get("review_count"),
        decision_report_unreadable=unreadable,
        promotion_count=_coerce_count(safe.get("promotion_count")),
        promotion_ids=_coerce_ids(safe.get("promotion_ids")),
        health=_build_weekly_health(out_dir) if run_kind == "weekly" else None,
    )


def _coerce_count(value: object) -> int:
    """Corrupt-but-parseable summary fields degrade to 0, never crash."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_ids(value: object) -> tuple[str, ...]:
    """Only a real list/tuple counts — a bare string would iterate per-char."""
    if isinstance(value, (list, tuple)):
        return tuple(str(i) for i in value)
    return ()


def _read_summary(path: Path) -> dict | None:
    """Return decision_report.json's `summary` dict.

    Returns:
        dict  — parsed summary (may be empty if key absent or null).
        None  — file exists but could not be parsed (P1-1 corrupt sentinel).
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("summary", {}) or {}
    except json.JSONDecodeError:
        _log.warning("could not parse decision_report.json — classifying as failed")
        return None


def _read_json(path: Path) -> dict | None:
    """Parse a JSON file → dict; unreadable/corrupt → None (never raises)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_monitor_health(root: Path, out_dir: Path) -> HealthDigest:
    try:
        trace = _read_json(out_dir / "monitor" / "eval_trace.json")
        flow = _read_json(root / "data" / "monitor" / "fund_flow_series.json")
        if trace is None or flow is None:
            return health_unknown()
        return monitor_health(
            trace, flow, today=_china_today(), holidays=frozenset(_load_holidays(root))
        )
    except Exception:  # noqa: BLE001 — never block notify (ADR 0016 AC8)
        _log.warning("monitor health gathering failed", exc_info=True)
        return health_unknown()


def _build_weekly_health(out_dir: Path) -> HealthDigest:
    try:
        gold = _read_json(out_dir / "gold_regime.json")
        if gold is None:
            return health_unknown()
        return weekly_health(gold, today=_china_today())
    except Exception:  # noqa: BLE001
        _log.warning("weekly health gathering failed", exc_info=True)
        return health_unknown()


def _is_iso_date(name: str) -> bool:
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _recent_rotation_statuses(root: Path, today: date, *, limit: int = 5) -> tuple[str, ...]:
    """data_status of the most-recent dated output dirs (<= today), newest first."""
    base = root / "outputs"
    if not base.exists():
        return ()
    dates = sorted(
        (p.name for p in base.iterdir()
         if p.is_dir() and _is_iso_date(p.name) and p.name <= today.isoformat()),
        reverse=True,
    )[:limit]
    out: list[str] = []
    for d in dates:
        radar = _read_json(base / d / "rotation" / "rotation_radar.json")
        if radar and radar.get("data_status"):
            out.append(str(radar["data_status"]))
    return tuple(out)


def _flow_capture_coverage(flow: dict, today: date) -> tuple[int, int]:
    """(symbols whose newest row == today, total symbols)."""
    iso = today.isoformat()
    at = 0
    for rows in flow.values():
        dates = [r[0] for r in rows if isinstance(r, (list, tuple)) and r]
        if dates and max(dates) == iso:
            at += 1
    return at, len(flow)


def _recovery_notice(radar: dict, recent: tuple[str, ...]) -> str | None:
    """Fire once on abstain/degraded → ok. recent[0] is today; recent[1] is prior."""
    if (radar or {}).get("data_status") != "ok":
        return None
    prior = recent[1] if len(recent) > 1 else None
    if prior is None or not (prior == "abstain" or str(prior).startswith("degraded_")):
        return None
    boards = len((radar or {}).get("board_states") or [])
    days = 0
    for s in recent[1:]:
        if s == "abstain" or str(s).startswith("degraded_"):
            days += 1
        else:
            break
    return f"轮动雷达恢复 ok ({boards} boards) — 此前弃权 {days} 日"


def _build_flow_capture_health(root: Path, out_dir: Path) -> tuple[HealthDigest, str | None]:
    try:
        radar = _read_json(out_dir / "rotation" / "rotation_radar.json")
        if radar is None:
            return health_unknown(), None
        recent = _recent_rotation_statuses(root, _china_today())
        flow = _read_json(root / "data" / "monitor" / "fund_flow_series.json")
        cov = _flow_capture_coverage(flow, _china_today()) if flow is not None else None
        return rotation_health(radar, recent, flow_capture_cov=cov), _recovery_notice(radar, recent)
    except Exception:  # noqa: BLE001
        _log.warning("flow-capture health gathering failed", exc_info=True)
        return health_unknown(), None


def _send_macos(decision: NotificationDecision) -> None:
    """Issue a macOS user notification via osascript (effect)."""
    title, body = format_macos(decision)
    script = f'display notification "{body}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def _send_feishu(decision: NotificationDecision, url: str) -> None:
    """POST the Feishu payload (effect). Logs host only — never the full URL."""
    payload = format_feishu(decision)
    _log.info("posting Feishu notification to host=%s", urlsplit(url).hostname or "?")
    resp = httpx.post(url, json=payload, timeout=10.0)
    resp.raise_for_status()


def _resolve_notify_on_clean(flag: bool | None) -> bool:
    """CLI flag wins; else IRC_NOTIFY_ON_CLEAN env; else default True."""
    if flag is not None:
        return flag
    raw = os.environ.get(_CLEAN_ENV, "").strip().lower()
    return raw in _TRUE if raw else True


def _dispatch(decision: NotificationDecision) -> int:
    """Send both channels independently. Returns 0 on full success, 1 if any
    channel failed. Never raises — a broken channel must not block the other."""
    if not decision.should_notify:
        return 0
    rc = 0
    try:
        _send_macos(decision)
    except Exception:  # noqa: BLE001 — degrade-never-crash (ADR 0016 / AC8)
        _log.warning("macOS notification failed", exc_info=True)
        rc = 1
    url = os.environ.get(_FEISHU_ENV, "").strip()
    if url:
        try:
            _send_feishu(decision, url)
        except Exception:  # noqa: BLE001 — degrade-never-crash
            _log.warning("Feishu notification failed", exc_info=True)
            rc = 1
    return rc


def run_notify_status(
    *,
    repo_root: str,
    run_kind: str,
    last_exit_code: int,
    notify_on_clean: bool | None,
) -> int:
    """Read artifacts → classify → dispatch. Returns the dispatch exit code."""
    root = Path(repo_root)
    outcome = _build_outcome(root, run_kind=run_kind, last_exit_code=last_exit_code)
    decision = classify_run_outcome(
        outcome, notify_on_clean=_resolve_notify_on_clean(notify_on_clean)
    )
    _log.info(
        "notify-status severity=%s notify=%s", decision.severity, decision.should_notify
    )
    return _dispatch(decision)
