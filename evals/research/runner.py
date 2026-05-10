from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.research.metrics import theme_coverage, ldr_citation_validity

_TZ = timezone(timedelta(hours=8))
_THEME_TH = {"warn_below": 7, "fail_below": 5}
_CITATION_TH = {"warn_below": 0.9, "fail_below": 0.7}


def run(repo_root: Path) -> int:
    research_file = repo_root / "outputs" / "research" / "reports.json"
    if not research_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"research eval: {report.overall} (no input file)")
        return 0

    reports: list[dict] = json.loads(research_file.read_text(encoding="utf-8"))

    tc = theme_coverage(reports)
    cv = ldr_citation_validity(reports)

    metrics: list[MetricReport] = [
        MetricReport(
            name="theme_coverage",
            value=float(tc),
            status=classify_status(float(tc), _THEME_TH, "higher_is_better"),
            n_observations=len(reports),
            threshold=_THEME_TH,
        ),
        MetricReport(
            name="ldr_citation_validity",
            value=cv,
            status=classify_status(cv, _CITATION_TH, "higher_is_better"),
            n_observations=len(reports),
            threshold=_CITATION_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="research",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(research_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"research eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="research", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "research")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
