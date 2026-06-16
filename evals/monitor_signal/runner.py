from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from evals._shared.locator import locate
from evals._shared.missing_input import (
    EVAL_RC_FAIL, EVAL_RC_PASS, EVAL_RC_WARN,
    missing_input_report, write_missing_input_report,
)
from evals._shared.report_paths import write_report
from evals._shared.report_schema import MetricReport, StageReport
from evals._shared.status import classify_status, worst_status
from evals.monitor_signal.metrics import (
    citation_resolution, nav_completeness, oracle_signal_match,
)

_TZ = timezone(timedelta(hours=8))
_ORACLE_TH = {"fail_below": 1.0}
_CITATION_TH = {"fail_below": 1.0}
_NAV_TH = {"warn_below": 0.85, "fail_below": 0.6}


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("monitor/eval_trace.json",))
    if located is None:
        report = missing_input_report(
            stage="monitor_signal",
            reason="outputs/<date>/monitor/eval_trace.json missing — monitor did not run",
            based_on_path="outputs/<date>/monitor/eval_trace.json (or latest)",
        )
        write_missing_input_report(repo_root, report)
        print("monitor_signal eval: FAIL (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    trace = json.loads(source.read_text(encoding="utf-8"))
    n = len(trace.get("funds", {}))

    oracle = oracle_signal_match(trace)
    citation = citation_resolution(trace)
    nav = nav_completeness(trace)
    metrics = [
        MetricReport("oracle_signal_match", oracle,
                     classify_status(oracle, _ORACLE_TH, "higher_is_better"), n, _ORACLE_TH),
        MetricReport("citation_resolution", citation,
                     classify_status(citation, _CITATION_TH, "higher_is_better"), n, _CITATION_TH),
        MetricReport("nav_completeness", nav,
                     classify_status(nav, _NAV_TH, "higher_is_better"), n, _NAV_TH),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="monitor_signal", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)], metrics=metrics, overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"monitor_signal eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (
        EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
