from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.locator import locate
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
from evals.memo.metrics import seven_sections_present, verbatim_ref_rate


_TZ = timezone(timedelta(hours=8))
_SECTIONS_TH = {"warn_below": 1.0, "fail_below": 0.75}
_VERBATIM_TH = {"warn_below": 0.9, "fail_below": 0.7}

_DEFERRED_METRICS_NOTE = (
    "Phase 2 redesign required for: auditor_no_factual_flags, "
    "length_drift_vs_baseline — current producer writes free-form "
    "memo_audit.txt and no baseline-chars sidecar."
)


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("memo.md", "memo_traceability.json"))
    if located is None:
        report = missing_input_report(
            stage="memo",
            reason=(
                "no outputs/<date>/ contains both memo.md and memo_traceability.json — "
                "memo stage did not run"
            ),
            based_on_path="outputs/<date>/memo.md + memo_traceability.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"memo eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    memo_path, traceability_path = located.paths
    memo_text = memo_path.read_text(encoding="utf-8")
    traceability = json.loads(traceability_path.read_text(encoding="utf-8"))

    sections = seven_sections_present(memo_text)
    verbatim = verbatim_ref_rate(traceability)

    metrics: list[MetricReport] = [
        MetricReport(
            name="seven_sections_present", value=sections,
            status=classify_status(sections, _SECTIONS_TH, "higher_is_better"),
            n_observations=8, threshold=_SECTIONS_TH,
        ),
        MetricReport(
            name="verbatim_ref_rate", value=verbatim,
            status=classify_status(verbatim, _VERBATIM_TH, "higher_is_better"),
            n_observations=int(traceability.get("n_refs_provided", 0)),
            threshold=_VERBATIM_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="memo",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(p) for p in located.paths],
        metrics=metrics,
        overall=overall,
        notes=_DEFERRED_METRICS_NOTE,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"memo eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
