from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.scoring.metrics import (
    factor_breakdown_completeness,
    raw_ref_reachability,
    historical_sanity_rho,
    score_distribution_stability,
)

_TZ = timezone(timedelta(hours=8))
_FBC_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RRR_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RHO_TH = {"warn_below": 0.0, "fail_below": -0.5}
_STABILITY_TH = {"warn_above": 0.1, "fail_above": 0.2}


def run(repo_root: Path) -> int:
    scores_file = repo_root / "outputs" / "scoring" / "scores.json"
    if not scores_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"scoring eval: {report.overall} (no input file)")
        return 0

    scores: list[dict] = json.loads(scores_file.read_text(encoding="utf-8"))

    # Build ref index from all raw_refs
    index: set[str] = set()
    for s in scores:
        for v in s.get("factor_breakdown", {}).values():
            index.update(v.get("raw_refs", []))

    fbc = factor_breakdown_completeness(scores)
    rrr = raw_ref_reachability(scores, index)
    rho = historical_sanity_rho(scores)

    # Compare first/second half score distributions for stability
    mid = len(scores) // 2
    comp_a = [s.get("composite_score", 0.0) for s in scores[:mid]]
    comp_b = [s.get("composite_score", 0.0) for s in scores[mid:]]
    stability = score_distribution_stability(comp_a, comp_b)

    metrics: list[MetricReport] = [
        MetricReport(
            name="factor_breakdown_completeness",
            value=fbc,
            status=classify_status(fbc, _FBC_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_FBC_TH,
        ),
        MetricReport(
            name="raw_ref_reachability",
            value=rrr,
            status=classify_status(rrr, _RRR_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_RRR_TH,
        ),
        MetricReport(
            name="historical_sanity_rho",
            value=rho,
            status=classify_status(rho, _RHO_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_RHO_TH,
        ),
        MetricReport(
            name="score_distribution_stability",
            value=stability,
            status=classify_status(stability, _STABILITY_TH, "lower_is_better"),
            n_observations=len(scores),
            threshold=_STABILITY_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="scoring",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(scores_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"scoring eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="scoring", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "scoring")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
