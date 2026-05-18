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
from evals.scoring.metrics import (
    buy_candidate_min_completeness,
    factor_breakdown_completeness,
    historical_sanity_rho,
    raw_ref_reachability,
    score_distribution_stability,
    scoring_data_completeness_avg,
)
from irc.decision.completeness import MIN_BUY_COMPLETENESS

_TZ = timezone(timedelta(hours=8))
_FBC_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RRR_TH = {"warn_below": 0.99, "fail_below": 0.9}
_RHO_TH = {"warn_below": 0.0, "fail_below": -0.5}
_STABILITY_TH = {"warn_above": 0.1, "fail_above": 0.2}
_DATA_COMPLETENESS_AVG_TH = {"warn_below": 0.90, "fail_below": 0.75}
# Spec: FAIL when any buy candidate < MIN_BUY_COMPLETENESS; no WARN band for buys.
_BUY_COMPLETENESS_TH = {"warn_below": MIN_BUY_COMPLETENESS, "fail_below": MIN_BUY_COMPLETENESS}


def _parse_scores(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return list(raw.get("scores", []))
    if isinstance(raw, list):
        return list(raw)
    return []


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("scoring.json",))
    if located is None:
        report = missing_input_report(
            stage="scoring",
            reason="outputs/<date>/scoring.json (or latest) is missing — scoring stage did not run",
            based_on_path="outputs/<date>/scoring.json (or latest)",
        )
        write_missing_input_report(repo_root, report)
        print(f"scoring eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    scores = _parse_scores(source)

    index: set[str] = set()
    for s in scores:
        for v in s.get("factor_breakdown", {}).values():
            index.update(v.get("raw_refs", []))

    fbc = factor_breakdown_completeness(scores)
    rrr = raw_ref_reachability(scores, index)
    rho = historical_sanity_rho(scores)
    data_completeness_avg = scoring_data_completeness_avg(scores)
    buy_min_completeness = buy_candidate_min_completeness(scores)

    mid = len(scores) // 2
    comp_a = [s.get("composite_score", 0.0) for s in scores[:mid]]
    comp_b = [s.get("composite_score", 0.0) for s in scores[mid:]]
    stability = score_distribution_stability(comp_a, comp_b)

    metrics: list[MetricReport] = [
        MetricReport(
            name="scoring_data_completeness_avg",
            value=data_completeness_avg,
            status=classify_status(data_completeness_avg, _DATA_COMPLETENESS_AVG_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_DATA_COMPLETENESS_AVG_TH,
        ),
        MetricReport(
            name="buy_candidate_min_completeness",
            value=buy_min_completeness,
            status=classify_status(buy_min_completeness, _BUY_COMPLETENESS_TH, "higher_is_better"),
            n_observations=len(scores),
            threshold=_BUY_COMPLETENESS_TH,
        ),
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
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"scoring eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
