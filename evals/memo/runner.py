from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import classify_status, worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict
from evals.memo.metrics import (
    seven_sections_present,
    raw_ref_reachability_in_memo,
    auditor_no_factual_flags,
    length_drift_vs_baseline,
)

_TZ = timezone(timedelta(hours=8))
_SECTIONS_TH = {"warn_below": 1.0, "fail_below": 0.75}
_REF_TH = {"warn_below": 0.9, "fail_below": 0.7}
_AUDIT_TH = {"warn_below": 0.9, "fail_below": 0.7}
_DRIFT_TH = {"warn_above": 1.3, "fail_above": 1.6}


def run(repo_root: Path) -> int:
    memo_file = repo_root / "outputs" / "memo" / "memo.md"
    if not memo_file.exists():
        report = _pass_report()
        _write(repo_root, report)
        print(f"memo eval: {report.overall} (no input file)")
        return 0

    memo_text = memo_file.read_text(encoding="utf-8")

    # Load audit result if available
    audit_file = repo_root / "outputs" / "memo" / "audit.json"
    audit_result: dict = {}
    if audit_file.exists():
        audit_result = json.loads(audit_file.read_text(encoding="utf-8"))

    # Load refs if available
    refs_file = repo_root / "outputs" / "memo" / "refs.json"
    refs: tuple[str, ...] = ()
    if refs_file.exists():
        refs = tuple(json.loads(refs_file.read_text(encoding="utf-8")))

    baseline_chars = int(repo_root / "outputs" / "memo" / "baseline_chars.txt").read_text().strip() \
        if (repo_root / "outputs" / "memo" / "baseline_chars.txt").exists() else len(memo_text)

    sp = seven_sections_present(memo_text)
    rr = raw_ref_reachability_in_memo(memo_text, refs)
    af = auditor_no_factual_flags(audit_result) if audit_result else 1.0
    ld = length_drift_vs_baseline(memo_text, baseline_chars)

    metrics: list[MetricReport] = [
        MetricReport(
            name="seven_sections_present",
            value=sp,
            status=classify_status(sp, _SECTIONS_TH, "higher_is_better"),
            n_observations=8,
            threshold=_SECTIONS_TH,
        ),
        MetricReport(
            name="raw_ref_reachability_in_memo",
            value=rr,
            status=classify_status(rr, _REF_TH, "higher_is_better"),
            n_observations=len(refs),
            threshold=_REF_TH,
        ),
        MetricReport(
            name="auditor_no_factual_flags",
            value=af,
            status=classify_status(af, _AUDIT_TH, "higher_is_better"),
            n_observations=audit_result.get("total_claims", 0),
            threshold=_AUDIT_TH,
        ),
        MetricReport(
            name="length_drift_vs_baseline",
            value=ld,
            status=classify_status(ld, _DRIFT_TH, "lower_is_better"),
            n_observations=1,
            threshold=_DRIFT_TH,
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="memo",
        ran_at=datetime.now(_TZ).isoformat(),
        based_on=[str(memo_file)],
        metrics=metrics,
        overall=overall,
    )
    _write(repo_root, report)
    print(f"memo eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _pass_report() -> StageReport:
    return StageReport(
        stage="memo", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "memo")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
