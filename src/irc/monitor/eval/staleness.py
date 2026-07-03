"""PURE: latest suite StageReport → StageHealth for the gate (roadmap §3.5).
M0 unit-tests this but does NOT wire it into apply_eval_gate (OQ3) — M1 does."""
from __future__ import annotations
from datetime import datetime
from evals._shared.report_schema import StageReport
from irc.monitor.eval.types import StageHealth

STALE_AFTER_DAYS = 14


def resolve_health(
    report: StageReport | None, *, now: datetime, stale_after_days: int,
    stage: str,
) -> StageHealth:
    if report is None:
        return StageHealth(stage, "UNKNOWN", ("absent",))
    if report.overall == "SKIPPED":
        return StageHealth(report.stage, "UNKNOWN", ("skipped",))
    try:
        ran_at = datetime.fromisoformat(report.ran_at)
    except (ValueError, TypeError):
        return StageHealth(report.stage, "UNKNOWN", ("corrupt_ran_at",))
    if ran_at.tzinfo is None:
        ran_at = ran_at.replace(tzinfo=now.tzinfo)
    age_days = (now - ran_at).days
    if age_days > stale_after_days:
        return StageHealth(report.stage, "UNKNOWN", (f"stale, {age_days}d",))
    failing = tuple(m.name for m in report.metrics if m.status in ("FAIL", "WARN"))
    return StageHealth(report.stage, report.overall, failing)  # type: ignore[arg-type]
