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
from evals.architecture.metrics import dag_acyclic_check, max_file_loc, output_files_present


def run(repo_root: Path) -> int:
    dag_ok = dag_acyclic_check(repo_root / "src" / "irc")
    max_loc = max_file_loc(repo_root / "src" / "irc")
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    out_dir = repo_root / "outputs" / today
    
    # If output directory doesn't exist, return FAIL (missing input pattern)
    if not out_dir.exists():
        report = missing_input_report(
            stage="architecture",
            reason="outputs/ is missing — architecture stage did not run",
            based_on_path="outputs/",
        )
        write_missing_input_report(repo_root, report)
        print(f"architecture eval: {report.overall} (no input file)")
        return EVAL_RC_FAIL
    
    files = output_files_present(out_dir)
    metrics = [
        MetricReport(
            name="dag_acyclic", value=1.0 if dag_ok else 0.0,
            status="PASS" if dag_ok else "FAIL",
            threshold={"fail_below": 1.0},
        ),
        MetricReport(
            name="max_file_loc", value=float(max_loc),
            status=classify_status(max_loc, {"warn_above": 400, "fail_above": 600},
                                    "lower_is_better"),
            threshold={"warn_above": 400, "fail_above": 600},
        ),
        MetricReport(
            name="output_files_completeness", value=files["completeness"],
            status=classify_status(files["completeness"], {"warn_below": 1.0, "fail_below": 0.6},
                                    "higher_is_better"),
            threshold={"warn_below": 1.0, "fail_below": 0.6},
        ),
    ]
    overall = worst_status([m.status for m in metrics])
    report = StageReport(
        stage="architecture",
        ran_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        based_on=[str(repo_root / "src" / "irc")],
        metrics=metrics, overall=overall,
    )
    out_eval = out_dir / "evals" / "architecture"
    out_eval.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_eval / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    print(f"architecture eval: {overall}")
    return 0 if overall == "PASS" else (1 if overall == "WARN" else 2)


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(timezone(timedelta(hours=8))).date().isoformat() / "evals" / "architecture")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
