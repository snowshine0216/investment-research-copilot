"""PURE outcome classifier. No file, clock, or env access — every input
arrives on `RunOutcome`. Precedence is locked by ADR 0016 §4/§5 + spec
§Classification.
"""
from __future__ import annotations

from irc.notify.types import NotificationDecision, RunOutcome

_EXIT_LABELS: dict[int, str] = {
    1: "runtime error",
    2: "config error",
    3: "fetch-budget exceeded",
    4: "lock conflict",
    5: "spend-gate stop",
}

_ALWAYS_NOTIFY = {"failed", "halted", "stale", "action"}


def classify_run_outcome(
    outcome: RunOutcome, *, notify_on_clean: bool = True
) -> NotificationDecision:
    """Map a RunOutcome to a NotificationDecision in fixed precedence."""
    severity, title, body = _decide(outcome)
    should_notify = severity in _ALWAYS_NOTIFY or (
        severity == "clean" and notify_on_clean
    )
    return NotificationDecision(
        should_notify=should_notify, severity=severity, title=title, body=body
    )


def _decide(outcome: RunOutcome) -> tuple[str, str, str]:
    if not outcome.today_dir_exists:
        return (
            "failed",
            "IRC run failed — no output",
            "No outputs/<today>/ — the scheduled run never produced output.",
        )
    if outcome.last_exit_code in _EXIT_LABELS:
        label = _EXIT_LABELS[outcome.last_exit_code]
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
    return outcome.actionable_buy_count > 0 or sells > 0


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
    return " · ".join(parts)
