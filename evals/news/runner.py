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
from evals.news.metrics import coverage_per_topic_per_week, dedup_rate, citation_reachability

_TZ = timezone(timedelta(hours=8))
_COVERAGE_TH = {"warn_below": 3, "fail_below": 1}
_DEDUP_TH = {"warn_below": 0.8, "fail_below": 0.5}
_CITATION_TH = {"warn_below": 0.9, "fail_below": 0.7}


def run(repo_root: Path) -> int:
    news_file = repo_root / "outputs" / "news" / "articles.json"
    if not news_file.exists():
        report = missing_input_report(
            stage="news",
            reason="outputs/news/articles.json is missing — news stage did not run",
            based_on_path="outputs/news/articles.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"news eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    articles: list[dict] = json.loads(news_file.read_text(encoding="utf-8"))

    coverage = coverage_per_topic_per_week(articles)
    min_coverage = min(coverage.values(), default=0)
    dr = dedup_rate(articles)
    cr = citation_reachability(articles)

    metrics: list[MetricReport] = [
        MetricReport(
            name="coverage_per_topic_per_week_min",
            value=float(min_coverage),
            status=classify_status(float(min_coverage), _COVERAGE_TH, "higher_is_better"),
            n_observations=len(coverage),
            threshold=_COVERAGE_TH,
        ),
        MetricReport(
            name="dedup_rate",
            value=dr,
            status=classify_status(dr, _DEDUP_TH, "higher_is_better"),
            n_observations=len(articles),
            threshold=_DEDUP_TH,
        ),
        MetricReport(
            name="citation_reachability",
            value=cr,
            status=classify_status(cr, _CITATION_TH, "higher_is_better"),
            n_observations=len(articles),
            threshold=_CITATION_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="news",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(news_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"news eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="news", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "news")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
