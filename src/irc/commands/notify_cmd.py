"""EDGE: read today's artifacts → RunOutcome → classify → dispatch.

All effects live here: `_china_today` (clock), `_build_outcome`/`_load_holidays`
(filesystem), `_send_macos` (osascript via subprocess), `_send_feishu` (httpx
POST). The pure logic is imported from `irc.notify`. A transport failure logs
and sets a non-zero return WITHOUT raising — a broken notifier must never mask
the underlying run result (ADR 0016 / AC8).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from irc.commands.notify_health import (
    read_flow_capture,
    read_monitor_health,
    read_weekly_health,
)
from irc.notify.classify import classify_run_outcome
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
    today = _china_today()
    out_dir = root / "outputs" / today.isoformat()
    if run_kind == "flow-capture":
        return _flow_capture_outcome(root, today, last_exit_code)
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
            health=read_monitor_health(root, today, _load_holidays(root)),
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
    outcome = RunOutcome(
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
    )
    if run_kind == "weekly":
        return dataclasses.replace(outcome, health=read_weekly_health(root, today))
    return outcome


def _flow_capture_outcome(root: Path, today: date, last_exit_code: int) -> RunOutcome:
    """Flow-capture: severity is health-driven (abstain/degraded → degraded); a
    rotation crash surfaces as `failed` via the missing radar sentinel. Sell-side
    counts are 0 (not None) so a clean base never reads as 'sell-side UNKNOWN'."""
    sentinel = root / "outputs" / today.isoformat() / "rotation" / "rotation_radar.json"
    digest, force = read_flow_capture(root, today)
    return RunOutcome(
        run_kind="flow-capture",
        last_exit_code=last_exit_code,
        today_dir_exists=sentinel.exists(),
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
        health=digest,
        force_notify=force,
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
