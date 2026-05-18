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
from evals.gold_score.metrics import (
    gold_regime_schema_completeness,
    gold_score_in_range,
    gold_tilt_valid_enum,
)


_TZ = timezone(timedelta(hours=8))
_SCHEMA_TH = {"warn_below": 1.0, "fail_below": 0.7}
_BINARY_TH = {"warn_below": 1.0, "fail_below": 1.0}

_DEFERRED_METRICS_NOTE = (
    "Phase 2 redesign required for: drivers_freshness, regime_flip_4w, "
    "tilt_within_preferences_band — current producer does not write the "
    "drivers / regime_history / preferences_band fields these metrics need."
)


def run(repo_root: Path) -> int:
    located = locate(repo_root, ("gold_regime.json", "gold_band.yaml"))
    if located is None:
        report = missing_input_report(
            stage="gold_score",
            reason=(
                "no outputs/<date>/ contains both gold_regime.json and gold_band.yaml — "
                "gold stage did not run"
            ),
            based_on_path="outputs/<date>/gold_regime.json + gold_band.yaml",
        )
        write_missing_input_report(repo_root, report)
        print(f"gold_score eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    regime_path = located.paths[0]
    regime = json.loads(regime_path.read_text(encoding="utf-8"))

    schema = gold_regime_schema_completeness(regime)
    tilt_ok = gold_tilt_valid_enum(regime.get("tilt"))
    score_ok = gold_score_in_range(regime.get("score"))

    metrics: list[MetricReport] = [
        MetricReport(
            name="gold_regime_schema_completeness", value=schema,
            status=classify_status(schema, _SCHEMA_TH, "higher_is_better"),
            n_observations=1, threshold=_SCHEMA_TH,
        ),
        MetricReport(
            name="gold_tilt_valid_enum", value=tilt_ok,
            status=classify_status(tilt_ok, _BINARY_TH, "higher_is_better"),
            n_observations=1, threshold=_BINARY_TH,
        ),
        MetricReport(
            name="gold_score_in_range", value=score_ok,
            status=classify_status(score_ok, _BINARY_TH, "higher_is_better"),
            n_observations=1, threshold=_BINARY_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="gold_score",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(p) for p in located.paths],
        metrics=metrics,
        overall=overall,
        notes=_DEFERRED_METRICS_NOTE,
    )
    write_report(repo_root, report, artifact_date=located.artifact_date)
    print(f"gold_score eval: {overall}")
    return EVAL_RC_PASS if overall == "PASS" else (EVAL_RC_WARN if overall == "WARN" else EVAL_RC_FAIL)
