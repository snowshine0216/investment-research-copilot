"""Shared 'eval input missing' report builder.

Replaces the historical 'missing input → PASS' pattern in every runner.
A missing input file means the upstream stage did not run (or crashed before
writing). Treating that as PASS lets broken pipelines look healthy. We treat
it as FAIL with exit code 2 so the CLI returns non-zero and dashboards turn red.

Path construction is delegated to ``evals._shared.report_paths.write_report``
so there is one location producing ``outputs/<date>/evals/<stage>/report.json``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.report_paths import write_report
from evals._shared.report_schema import StageReport


EVAL_RC_PASS = 0
EVAL_RC_WARN = 1
EVAL_RC_FAIL = 2

_TZ = timezone(timedelta(hours=8))
_SECS_PER_DAY = 86_400.0


def input_age_days(path: Path) -> float:
    """Return file age in fractional days based on mtime."""
    return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / _SECS_PER_DAY


def missing_input_report(
    *,
    stage: str,
    reason: str,
    based_on_path: str | None,
) -> StageReport:
    """Build a FAIL StageReport indicating the eval's input was absent."""
    based_on = [based_on_path] if based_on_path else []
    return StageReport(
        stage=stage,
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=based_on,
        metrics=[],
        overall="FAIL",
        notes=reason,
    )


def write_missing_input_report(
    repo_root: Path, report: StageReport, *, date_str: str | None = None,
) -> Path:
    """Write the FAIL report under the run date (default) or a caller-supplied date."""
    if date_str is None:
        date_str = datetime.now(_TZ).date().isoformat()
    return write_report(repo_root, report, artifact_date=date_str)
