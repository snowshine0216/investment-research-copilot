from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    EVAL_RC_PASS,
    EVAL_RC_WARN,
    missing_input_report,
    write_missing_input_report,
)
from evals._shared.report_paths import write_report
from evals._shared.report_schema import MetricReport, StageReport
from evals._shared.status import classify_status, worst_status
from evals.architecture.metrics import (
    dag_acyclic_check,
    max_file_loc,
    output_files_present,
)


_TZ = timezone(timedelta(hours=8))
_DATE_LEN = 10


def _is_date_dir(name: str) -> bool:
    if len(name) != _DATE_LEN:
        return False
    try:
        date.fromisoformat(name)
        return True
    except ValueError:
        return False


def _today_iso() -> str:
    return datetime.now(_TZ).date().isoformat()


def _latest_dated_outputs_dir(repo_root: Path) -> tuple[Path, str] | None:
    """Pick today's outputs dir if it exists, else the latest dated dir.

    Unlike the shared locator, this does NOT require any files to be present —
    the architecture runner wants to measure completeness of an existing dated
    directory, which means it must accept directories that are merely
    partially populated.
    """
    outputs = repo_root / "outputs"
    if not outputs.is_dir():
        return None
    today = _today_iso()
    today_dir = outputs / today
    if today_dir.is_dir():
        return (today_dir, today)
    candidates = sorted(
        (d for d in outputs.iterdir() if d.is_dir() and _is_date_dir(d.name)),
        key=lambda p: p.name, reverse=True,
    )
    return (candidates[0], candidates[0].name) if candidates else None


def run(repo_root: Path) -> int:
    located = _latest_dated_outputs_dir(repo_root)
    if located is None:
        report = missing_input_report(
            stage="architecture",
            reason="outputs/ contains no dated output directory — pipeline has not run",
            based_on_path="outputs/",
        )
        write_missing_input_report(repo_root, report)
        print(f"architecture eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    out_dir, artifact_date = located
    dag_ok = dag_acyclic_check(repo_root / "src" / "irc")
    max_loc = max_file_loc(repo_root / "src" / "irc")
    files = output_files_present(out_dir)

    metrics: list[MetricReport] = [
        MetricReport(
            name="dag_acyclic", value=1.0 if dag_ok else 0.0,
            status="PASS" if dag_ok else "FAIL",
            threshold={"fail_below": 1.0},
        ),
        MetricReport(
            name="max_file_loc", value=float(max_loc),
            status=classify_status(
                max_loc, {"warn_above": 400, "fail_above": 600}, "lower_is_better"
            ),
            threshold={"warn_above": 400, "fail_above": 600},
        ),
        MetricReport(
            name="output_files_completeness", value=files["completeness"],
            status=classify_status(
                files["completeness"], {"warn_below": 1.0, "fail_below": 0.6},
                "higher_is_better",
            ),
            threshold={"warn_below": 1.0, "fail_below": 0.6},
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="architecture",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(repo_root / "src" / "irc"), str(out_dir)],
        metrics=metrics,
        overall=overall,
    )
    write_report(repo_root, report, artifact_date=artifact_date)
    print(f"architecture eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
