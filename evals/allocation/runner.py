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
from evals.allocation.metrics import effective_n, weight_sum


_TZ = timezone(timedelta(hours=8))
_WSUM_TH = {"warn_above": 0.001, "fail_above": 0.01}
_EN_TH = {"warn_below": 4, "fail_below": 2}

_DEFERRED_METRICS_NOTE = (
    "Phase 2 redesign required for: in_band_per_class, currency_in_tolerance, "
    "max_pair_correlation_1y — current producer does not write class_bands / "
    "currency_targets / currency_exposure / correlation_matrix_1y fields."
)


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("proposed_allocation.yaml",))
    if located is None:
        report = missing_input_report(
            stage="allocation",
            reason="outputs/<date>/proposed_allocation.yaml is missing — allocation stage did not run",
            based_on_path="outputs/<date>/proposed_allocation.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"allocation eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    source = located.paths[0]
    data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}

    ws_dev = abs(weight_sum(data) - 1.0)
    en = effective_n(data)

    metrics: list[MetricReport] = [
        MetricReport(
            name="weight_sum_deviation", value=ws_dev,
            status=classify_status(ws_dev, _WSUM_TH, "lower_is_better"),
            n_observations=1, threshold=_WSUM_TH,
        ),
        MetricReport(
            name="effective_n", value=en,
            status=classify_status(en, _EN_TH, "higher_is_better"),
            n_observations=len(data.get("selected_instruments", [])),
            threshold=_EN_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="allocation",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(source)],
        metrics=metrics,
        overall=overall,
        notes=_DEFERRED_METRICS_NOTE,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"allocation eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
