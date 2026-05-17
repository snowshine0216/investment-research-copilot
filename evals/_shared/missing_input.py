"""Shared 'eval input missing' report builder.

Replaces the historical 'missing input → PASS' pattern in every runner.
A missing input file means the upstream stage did not run (or crashed before
writing). Treating that as PASS lets broken pipelines look healthy. We treat
it as FAIL with exit code 2 so the CLI returns non-zero and dashboards turn red.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.report_schema import StageReport, report_to_dict
from irc.io_utils import atomic_write_text


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
    """Write the FAIL report under outputs/<date>/evals/<stage>/report.json."""
    if date_str is None:
        date_str = datetime.now(_TZ).date().isoformat()
    out_dir = repo_root / "outputs" / date_str / "evals" / report.stage
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "report.json"
    atomic_write_text(
        out, json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)
    )
    return out
