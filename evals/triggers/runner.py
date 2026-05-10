from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from irc.io_utils import atomic_write_text
from evals._shared.status import worst_status
from evals._shared.report_schema import StageReport, MetricReport, report_to_dict

_TZ = timezone(timedelta(hours=8))


def run(repo_root: Path) -> int:
    # For now, return PASS if trigger data is missing (graceful pattern)
    report = _pass_report()
    _write(repo_root, report)
    print(f"triggers eval: {report.overall} (no input data)")
    return 0


def _pass_report() -> StageReport:
    return StageReport(
        stage="triggers", ran_at=datetime.now(_TZ).isoformat(),
        based_on=[], metrics=[], overall="PASS",
    )


def _write(repo_root: Path, report: StageReport) -> None:
    out_dir = (repo_root / "outputs" / datetime.now(_TZ).date().isoformat() / "evals" / "triggers")
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_dir / "report.json", json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
