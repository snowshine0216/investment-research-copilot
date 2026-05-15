from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.research.metrics import (
    theme_coverage,
    research_success_rate,
    research_citation_validity,
    research_failure_visibility,
)

_TZ = timezone(timedelta(hours=8))
_THEME_TH = {"warn_below": 7, "fail_below": 5}
_SUCCESS_TH = {"warn_below": 0.8, "fail_below": 0.5}
_CITATION_TH = {"warn_below": 0.9, "fail_below": 0.7}
_VISIBILITY_TH = {"warn_below": 1.0, "fail_below": 0.9}


def run(repo_root: Path) -> int:
    status_file = repo_root / "data" / "research" / "research_status.json"
    if not status_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"research eval: {report.overall} (no input file)")
        return 0

    body = json.loads(status_file.read_text(encoding="utf-8"))
    themes: list[dict] = body.get("themes", [])

    tc = theme_coverage(themes)
    sr = research_success_rate(themes)
    cv = research_citation_validity(themes)
    fv = research_failure_visibility(themes)

    metrics: list[MetricReport] = [
        MetricReport(
            name="theme_coverage",
            value=float(tc),
            status=classify_status(float(tc), _THEME_TH, "higher_is_better"),
            n_observations=len(themes),
            threshold=_THEME_TH,
        ),
        MetricReport(
            name="research_success_rate",
            value=sr,
            status=classify_status(sr, _SUCCESS_TH, "higher_is_better"),
            n_observations=len(themes),
            threshold=_SUCCESS_TH,
        ),
        MetricReport(
            name="research_citation_validity",
            value=cv,
            status=classify_status(cv, _CITATION_TH, "higher_is_better"),
            n_observations=len(themes),
            threshold=_CITATION_TH,
        ),
        MetricReport(
            name="research_failure_visibility",
            value=fv,
            status=classify_status(fv, _VISIBILITY_TH, "higher_is_better"),
            n_observations=len(themes),
            threshold=_VISIBILITY_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="research",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(status_file)],
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
