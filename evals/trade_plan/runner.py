from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.trade_plan.metrics import (
    venue_compatibility_marked,
    buy_method_class_match,
    trigger_monitorability,
)

_TZ = timezone(timedelta(hours=8))
_VENUE_TH = {"warn_below": 1.0, "fail_below": 0.9}
_METHOD_TH = {"warn_below": 1.0, "fail_below": 0.9}
_TRIGGER_TH = {"warn_below": 1.0, "fail_below": 0.9}


def run(repo_root: Path) -> int:
    plan_file = repo_root / "outputs" / "trade_plan" / "trades.json"
    if not plan_file.exists():
        report = missing_input_report(
            stage="trade_plan",
            reason="outputs/trade_plan/trades.json is missing — trade_plan stage did not run",
            based_on_path="outputs/trade_plan/trades.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"trade_plan eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    trades: list[dict] = json.loads(plan_file.read_text(encoding="utf-8"))

    vc = venue_compatibility_marked(trades)
    bm = buy_method_class_match(trades)
    tm = trigger_monitorability(trades)

    metrics: list[MetricReport] = [
        MetricReport(
            name="venue_compatibility_marked",
            value=vc,
            status=classify_status(vc, _VENUE_TH, "higher_is_better"),
            n_observations=len(trades),
            threshold=_VENUE_TH,
        ),
        MetricReport(
            name="buy_method_class_match",
            value=bm,
            status=classify_status(bm, _METHOD_TH, "higher_is_better"),
            n_observations=len(trades),
            threshold=_METHOD_TH,
        ),
        MetricReport(
            name="trigger_monitorability",
            value=tm,
            status=classify_status(tm, _TRIGGER_TH, "higher_is_better"),
            n_observations=len(trades),
            threshold=_TRIGGER_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="trade_plan",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(plan_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"trade_plan eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="trade_plan", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "trade_plan")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
