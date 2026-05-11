from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.queries.metrics import (
    median_response_time,
    citation_attached_per_response,
    internal_consistency_with_latest_memo,
)

_TZ = timezone(timedelta(hours=8))
_RT_TH = {"warn_above": 20, "fail_above": 30}
_CITATION_TH = {"warn_below": 1.0, "fail_below": 0.8}
_CONSISTENCY_TH = {"warn_below": 0.9, "fail_below": 0.7}


def run(repo_root: Path) -> int:
    queries_file = repo_root / "outputs" / "queries" / "queries.json"
    if not queries_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"queries eval: {report.overall} (no input file)")
        return 0

    queries: list[dict] = json.loads(queries_file.read_text(encoding="utf-8"))

    memo_file = repo_root / "outputs" / "memo" / "memo.md"
    memo_text = memo_file.read_text(encoding="utf-8") if memo_file.exists() else ""

    rt = median_response_time(queries)
    ca = citation_attached_per_response(queries)
    ic = internal_consistency_with_latest_memo(queries, memo_text)

    metrics: list[MetricReport] = [
        MetricReport(
            name="median_response_time_s",
            value=rt,
            status=classify_status(rt, _RT_TH, "lower_is_better"),
            n_observations=len(queries),
            threshold=_RT_TH,
        ),
        MetricReport(
            name="citation_attached_per_response",
            value=ca,
            status=classify_status(ca, _CITATION_TH, "higher_is_better"),
            n_observations=len(queries),
            threshold=_CITATION_TH,
        ),
        MetricReport(
            name="internal_consistency_with_latest_memo",
            value=ic,
            status=classify_status(ic, _CONSISTENCY_TH, "higher_is_better"),
            n_observations=len(queries),
            threshold=_CONSISTENCY_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="queries",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(queries_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"queries eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="queries", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "queries")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
