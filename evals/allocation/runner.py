from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.allocation.metrics import (
    weight_sum,
    in_band_per_class,
    effective_n,
    currency_in_tolerance,
    max_pair_correlation_1y,
)

_TZ = timezone(timedelta(hours=8))
_WSUM_TH = {"warn_above": 0.001, "fail_above": 0.01}
_EN_TH = {"warn_below": 4, "fail_below": 2}
_INBAND_TH = {"warn_below": 0.9, "fail_below": 0.7}
_CCY_TH = {"warn_below": 0.9, "fail_below": 0.7}
_CORR_TH = {"warn_above": 0.8, "fail_above": 0.95}


def run(repo_root: Path) -> int:
    alloc_file = repo_root / "outputs" / "allocation" / "allocation.json"
    if not alloc_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"allocation eval: {report.overall} (no input file)")
        return 0

    data: dict = json.loads(alloc_file.read_text(encoding="utf-8"))

    ws = weight_sum(data)
    ws_dev = abs(ws - 1.0)
    en = effective_n(data)

    bands = {k: tuple(v) for k, v in data.get("class_bands", {}).items()}
    inb = in_band_per_class(data, bands)

    targets = data.get("currency_targets", {})
    ccy = currency_in_tolerance(data, targets)

    corr_matrix = data.get("correlation_matrix_1y", {})
    max_corr = max_pair_correlation_1y(corr_matrix)

    metrics: list[MetricReport] = [
        MetricReport(
            name="weight_sum_deviation",
            value=ws_dev,
            status=classify_status(ws_dev, _WSUM_TH, "lower_is_better"),
            n_observations=1,
            threshold=_WSUM_TH,
        ),
        MetricReport(
            name="effective_n",
            value=en,
            status=classify_status(en, _EN_TH, "higher_is_better"),
            n_observations=len(data.get("selected_instruments", [])),
            threshold=_EN_TH,
        ),
        MetricReport(
            name="in_band_per_class",
            value=inb,
            status=classify_status(inb, _INBAND_TH, "higher_is_better"),
            n_observations=len(bands),
            threshold=_INBAND_TH,
        ),
        MetricReport(
            name="currency_in_tolerance",
            value=ccy,
            status=classify_status(ccy, _CCY_TH, "higher_is_better"),
            n_observations=len(targets),
            threshold=_CCY_TH,
        ),
        MetricReport(
            name="max_pair_correlation_1y",
            value=max_corr,
            status=classify_status(max_corr, _CORR_TH, "lower_is_better"),
            n_observations=len(corr_matrix),
            threshold=_CORR_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="allocation",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(alloc_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"allocation eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="allocation", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "allocation")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
