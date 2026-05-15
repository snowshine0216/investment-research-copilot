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
from evals.gold_score.metrics import drivers_freshness, regime_flip_4w, tilt_within_preferences_band

_TZ = timezone(timedelta(hours=8))
_FRESHNESS_TH = {"warn_above": 5, "fail_above": 7}
_FLIP_TH = {"warn_above": 2, "fail_above": 4}
_TILT_TH = {"warn_below": 0.8, "fail_below": 0.6}


def run(repo_root: Path) -> int:
    gold_file = repo_root / "outputs" / "gold_score" / "gold_score.json"
    if not gold_file.exists():
        report = missing_input_report(
            stage="gold_score",
            reason="outputs/gold_score/gold_score.json is missing — gold_score stage did not run",
            based_on_path="outputs/gold_score/gold_score.json",
        )
        write_missing_input_report(repo_root, report)
        print(f"gold_score eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL

    data: dict = json.loads(gold_file.read_text(encoding="utf-8"))

    drivers = data.get("drivers", [])
    freshness = drivers_freshness(drivers)
    max_age = max(freshness.values(), default=0)

    history = data.get("regime_history", [])
    flips = regime_flip_4w(history)

    tilt = data.get("tilt", {})
    prefs = {k: tuple(v) for k, v in data.get("preferences_band", {}).items()}
    tilt_ok = tilt_within_preferences_band(tilt, prefs)

    metrics: list[MetricReport] = [
        MetricReport(
            name="drivers_freshness_max_days",
            value=float(max_age),
            status=classify_status(float(max_age), _FRESHNESS_TH, "lower_is_better"),
            n_observations=len(drivers),
            threshold=_FRESHNESS_TH,
        ),
        MetricReport(
            name="regime_flip_4w",
            value=float(flips),
            status=classify_status(float(flips), _FLIP_TH, "lower_is_better"),
            n_observations=len(history),
            threshold=_FLIP_TH,
        ),
        MetricReport(
            name="tilt_within_preferences_band",
            value=tilt_ok,
            status=classify_status(tilt_ok, _TILT_TH, "higher_is_better"),
            n_observations=len(prefs),
            threshold=_TILT_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="gold_score",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(gold_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"gold_score eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="gold_score", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "gold_score")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
