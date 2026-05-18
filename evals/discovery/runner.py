from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

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
from evals.discovery.metrics import (
    candidates_per_role,
    dedup,
    filter_integrity,
    llm_reason_grounding,
)


_TZ = timezone(timedelta(hours=8))
_CAND_TH = {"warn_below": 8, "fail_below": 5}
_GROUND_TH = {"warn_below": 0.9, "fail_below": 0.7}
_INTEGRITY_TH = {"warn_below": 0.99, "fail_below": 0.9}
_DEDUP_TH = {"warn_below": 0.99, "fail_below": 0.9}

_REQUIRED_COLUMNS: tuple[str, ...] = ("instrument_id", "ticker", "role", "cited_refs")


def _missing_required(wl: pd.DataFrame) -> tuple[str, ...]:
    return tuple(c for c in _REQUIRED_COLUMNS if c not in wl.columns)


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("discovered_watchlist.csv",))
    if located is None:
        report = missing_input_report(
            stage="discovery",
            reason="outputs/<date>/discovered_watchlist.csv is missing — discovery stage did not run",
            based_on_path="outputs/<date>/discovered_watchlist.csv",
        )
        write_missing_input_report(repo_root, report)
        print(f"discovery eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    wl = pd.read_csv(source)

    missing = _missing_required(wl)
    if missing:
        report = StageReport(
            stage="discovery",
            ran_at=datetime.now(_TZ).isoformat(),
            based_on=[str(source)],
            metrics=[],
            overall="FAIL",
            notes=f"discovered_watchlist.csv missing required columns: {', '.join(missing)}",
        )
        write_report(repo_root, report, artifact_date=located.artifact_date)
        print(f"discovery eval: FAIL (schema mismatch — missing {', '.join(missing)})")
        return EVAL_RC_FAIL

    cpr = candidates_per_role(wl)
    min_cpr = min(cpr.values(), default=0)
    fi = filter_integrity(wl)
    dp = dedup(wl)
    gr = llm_reason_grounding(wl)

    metrics: list[MetricReport] = [
        MetricReport(
            name="candidates_per_role_min", value=float(min_cpr),
            status=classify_status(float(min_cpr), _CAND_TH, "higher_is_better"),
            n_observations=len(cpr), threshold=_CAND_TH,
        ),
        MetricReport(
            name="filter_integrity", value=fi,
            status=classify_status(fi, _INTEGRITY_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_INTEGRITY_TH,
        ),
        MetricReport(
            name="dedup", value=dp,
            status=classify_status(dp, _DEDUP_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_DEDUP_TH,
        ),
        MetricReport(
            name="llm_reason_grounding", value=gr,
            status=classify_status(gr, _GROUND_TH, "higher_is_better"),
            n_observations=len(wl), threshold=_GROUND_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="discovery",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"discovery eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
