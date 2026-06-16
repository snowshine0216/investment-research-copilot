"""PURE: latest suite StageReport → StageHealth for the gate (roadmap §3.5).
M0 unit-tests this but does NOT wire it into apply_eval_gate (OQ3) — M1 does."""
from __future__ import annotations
from datetime import datetime
from evals._shared.report_schema import StageReport
from irc.monitor.eval.types import StageHealth

STALE_AFTER_DAYS = 14


def resolve_health(
    report: StageReport | None, *, now: datetime, stale_after_days: int,
) -> StageHealth:
    if report is None:
        return StageHealth("monitor_suite", "UNKNOWN", ("absent",))
    if report.overall == "SKIPPED":
        return StageHealth(report.stage, "UNKNOWN", ("skipped",))
    ran_at = datetime.fromisoformat(report.ran_at)
    if (now - ran_at).days > stale_after_days:
        return StageHealth(report.stage, "UNKNOWN", ("stale",))
    return StageHealth(report.stage, report.overall, ())  # type: ignore[arg-type]
