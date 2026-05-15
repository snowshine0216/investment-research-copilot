from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import pandas as pd
from irc.io_utils import atomic_write_text
from evals._shared.missing_input import (
    EVAL_RC_FAIL,
    missing_input_report,
    write_missing_input_report,
)
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.discovery.metrics import candidates_per_role, filter_integrity, dedup, llm_reason_grounding

_TZ = timezone(timedelta(hours=8))
_CAND_TH = {"warn_below": 8, "fail_below": 5}
_GROUND_TH = {"warn_below": 0.9, "fail_below": 0.7}
_INTEGRITY_TH = {"warn_below": 0.99, "fail_below": 0.9}
_DEDUP_TH = {"warn_below": 0.99, "fail_below": 0.9}


def run(repo_root: Path) -> int:
    watchlist_file = repo_root / "outputs" / "discovery" / "watchlist.json"
    if not watchlist_file.exists():
        report = missing_input_report(
            stage="discovery",
            reason="outputs/discovery/watchlist.json is missing — discovery stage did not run",
            based_on_path="outputs/discovery/watchlist.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"discovery eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    records: list[dict] = json.loads(watchlist_file.read_text(encoding="utf-8"))
    wl = pd.DataFrame(records)

    cpr = candidates_per_role(wl)
    min_cpr = min(cpr.values(), default=0)
    fi = filter_integrity(wl)
    dp = dedup(wl)
    gr = llm_reason_grounding(wl)

    metrics: list[MetricReport] = [
        MetricReport(
            name="candidates_per_role_min",
            value=float(min_cpr),
            status=classify_status(float(min_cpr), _CAND_TH, "higher_is_better"),
            n_observations=len(cpr),
            threshold=_CAND_TH,
        ),
        MetricReport(
            name="filter_integrity",
            value=fi,
            status=classify_status(fi, _INTEGRITY_TH, "higher_is_better"),
            n_observations=len(wl),
            threshold=_INTEGRITY_TH,
        ),
        MetricReport(
            name="dedup",
            value=dp,
            status=classify_status(dp, _DEDUP_TH, "higher_is_better"),
            n_observations=len(wl),
            threshold=_DEDUP_TH,
        ),
        MetricReport(
            name="llm_reason_grounding",
            value=gr,
            status=classify_status(gr, _GROUND_TH, "higher_is_better"),
            n_observations=len(wl),
            threshold=_GROUND_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="discovery",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(watchlist_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"discovery eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="discovery", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "discovery")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
