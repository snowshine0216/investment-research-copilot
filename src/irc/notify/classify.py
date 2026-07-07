"""PURE outcome classifier. No file, clock, or env access — every input
arrives on `RunOutcome`. Precedence is locked by ADR 0016 §4/§5 + spec
§Classification.
"""
from __future__ import annotations

from irc.notify.health import HealthDigest
from irc.notify.types import NotificationDecision, RunOutcome

_EXIT_LABELS: dict[int, str] = {
    1: "runtime error",
    2: "config error",
    3: "fetch-budget exceeded",
    4: "lock conflict",
    5: "spend-gate stop",
    124: "timeout",  # P0-3: watchdog killed the pipeline after IRC_RUN_TIMEOUT
}

_ALWAYS_NOTIFY = {"failed", "halted", "stale", "degraded", "action"}


def classify_run_outcome(
    outcome: RunOutcome, *, notify_on_clean: bool = True
) -> NotificationDecision:
    """Map a RunOutcome to a NotificationDecision in fixed precedence."""
    severity, title, body = _decide(outcome)
    should_notify = severity in _ALWAYS_NOTIFY or (
        severity == "clean" and (notify_on_clean or outcome.recovery_notice is not None)
    )
    return NotificationDecision(
        should_notify=should_notify, severity=severity, title=title, body=body
    )


def _decide(outcome: RunOutcome) -> tuple[str, str, str]:
    """Base precedence, then health-degraded escalation + body append + recovery."""
    severity, title, body = _base_decide(outcome)
    health = outcome.health
    if severity in ("action", "clean") and health is not None and health.has_warnings:
        severity, title = "degraded", "IRC data degraded"
    if health is not None and health.has_warnings:
        body = _append_health(body, health)
    if severity == "clean" and outcome.recovery_notice:
        return ("clean", "IRC: 轮动雷达恢复", outcome.recovery_notice)
    return (severity, title, body)


def _append_health(body: str, health: HealthDigest) -> str:
    lines = " · ".join(i.text for i in health.items)
    return f"{body} · {lines}" if body else lines


def _base_decide(outcome: RunOutcome) -> tuple[str, str, str]:
    if not outcome.today_dir_exists:
        return (
            "failed",
            "IRC run failed — no output",
            "No outputs/<today>/ — the scheduled run never produced output.",
        )
    if outcome.decision_report_unreadable:
        return (
            "failed",
            "IRC run failed — report unreadable",
            "decision_report.json unreadable — file exists but could not be parsed.",
        )
    if outcome.last_exit_code != 0:
        label = _EXIT_LABELS.get(
            outcome.last_exit_code, f"exit {outcome.last_exit_code}"
        )
        return (
            "failed",
            f"IRC run failed — {label}",
            f"Exit {outcome.last_exit_code}. See PIPELINE_HALTED.md / the run log.",
        )
    if outcome.pipeline_halted:
        return (
            "halted",
            "IRC run halted",
            "PIPELINE_HALTED.md present — the pipeline stopped mid-run.",
        )
    if outcome.stale_ingest:
        return (
            "stale",
            "IRC data stale",
            "STALE_INGEST.md present — report may be built on old inputs.",
        )
    if _any_sell_unknown(outcome):
        return (
            "action",
            "IRC: sell-side state UNKNOWN",
            "Sell-side state unknown (stale artifact) — re-run `irc opportunity`.",
        )
    if _has_action(outcome):
        return ("action", "IRC: action required", _rollup_body(outcome))
    return ("clean", "IRC run clean", "Run completed; nothing actionable.")


def _any_sell_unknown(outcome: RunOutcome) -> bool:
    return None in (outcome.trim_count, outcome.exit_count, outcome.review_count)


def _has_action(outcome: RunOutcome) -> bool:
    sells = (
        (outcome.trim_count or 0) + (outcome.exit_count or 0) + (outcome.review_count or 0)
    )
    return outcome.actionable_buy_count > 0 or sells > 0 or outcome.promotion_count > 0


_MAX_PROMOTION_IDS_IN_BODY = 5


def _promotions_part(outcome: RunOutcome) -> str:
    ids = outcome.promotion_ids[:_MAX_PROMOTION_IDS_IN_BODY]
    listed = ", ".join(ids)
    if len(outcome.promotion_ids) > _MAX_PROMOTION_IDS_IN_BODY:
        listed += ", …"
    label = "promotion" if outcome.promotion_count == 1 else "promotions"
    return f"{outcome.promotion_count} {label} ({listed})"


def _rollup_body(outcome: RunOutcome) -> str:
    parts: list[str] = []
    if outcome.actionable_buy_count > 0:
        parts.append(f"{outcome.actionable_buy_count} buys")
    for count, label in (
        (outcome.trim_count, "trim"),
        (outcome.exit_count, "exit"),
        (outcome.review_count, "review"),
    ):
        if count:
            parts.append(f"{count} {label}")
    if outcome.promotion_count > 0:
        parts.append(_promotions_part(outcome))
    return " · ".join(parts)
