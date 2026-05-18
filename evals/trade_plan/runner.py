from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

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
from evals.trade_plan.metrics import (
    buy_method_class_match,
    trigger_monitorability,
    venue_compatibility_marked,
)


_TZ = timezone(timedelta(hours=8))
_VENUE_TH = {"warn_below": 1.0, "fail_below": 0.9}
_METHOD_TH = {"warn_below": 1.0, "fail_below": 0.9}
_TRIGGER_TH = {"warn_below": 1.0, "fail_below": 0.9}


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("trade_plan.yaml",))
    if located is None:
        report = missing_input_report(
            stage="trade_plan",
            reason="outputs/<date>/trade_plan.yaml is missing — trade_plan stage did not run",
            based_on_path="outputs/<date>/trade_plan.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"trade_plan eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    payload = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    trades = payload.get("trades", []) if isinstance(payload, dict) else []

    vc = venue_compatibility_marked(trades)
    bm = buy_method_class_match(trades)
    tm = trigger_monitorability(trades)

    metrics: list[MetricReport] = [
        MetricReport(
            name="venue_compatibility_marked", value=vc,
            status=classify_status(vc, _VENUE_TH, "higher_is_better"),
            n_observations=len(trades), threshold=_VENUE_TH,
        ),
        MetricReport(
            name="buy_method_class_match", value=bm,
            status=classify_status(bm, _METHOD_TH, "higher_is_better"),
            n_observations=len(trades), threshold=_METHOD_TH,
        ),
        MetricReport(
            name="trigger_monitorability", value=tm,
            status=classify_status(tm, _TRIGGER_TH, "higher_is_better"),
            n_observations=len(trades), threshold=_TRIGGER_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="trade_plan",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"trade_plan eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
