from __future__ import annotations
import json
from pathlib import Path
from evals._shared.latest_report import (
    StageReportEntry, list_stage_reports, latest_stage_report_entry,
    latest_stage_report,
)
from evals._shared.report_schema import StageReport, report_to_dict


def _write(root: Path, stage: str, date_str: str, ran_at: str, overall="PASS") -> None:
    d = root / "outputs" / date_str / "evals" / stage
    d.mkdir(parents=True)
    rep = StageReport(stage=stage, ran_at=ran_at, based_on=[], metrics=[], overall=overall)
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")


def test_entry_carries_artifact_date_from_dir_name():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        _write(root, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
        entry = latest_stage_report_entry(root, "monitor_forward", today_iso="2026-06-16")
        assert isinstance(entry, StageReportEntry)
        assert entry.artifact_date == "2026-06-14"
        assert entry.report.stage == "monitor_forward"


def test_list_descending_by_artifact_date(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-10", "2026-06-10T09:00:00+08:00")
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14", "2026-06-10"]


def test_list_applies_today_clamp(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    _write(tmp_path, "monitor_forward", "2026-06-20", "2026-06-20T09:00:00+08:00")  # future
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14"]


def test_list_limit(tmp_path: Path):
    for d in ("2026-06-10", "2026-06-12", "2026-06-14"):
        _write(tmp_path, "monitor_forward", d, f"{d}T09:00:00+08:00")
    out = list_stage_reports(tmp_path, "monitor_forward", limit=2, today_iso="2026-06-16")
    assert len(out) == 2 and out[0].artifact_date == "2026-06-14"


def test_list_skips_corrupt(tmp_path: Path):
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    bad = tmp_path / "outputs" / "2026-06-15" / "evals" / "monitor_forward"
    bad.mkdir(parents=True)
    (bad / "report.json").write_text("{bad}", encoding="utf-8")
    out = list_stage_reports(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert [e.artifact_date for e in out] == ["2026-06-14"]


def test_latest_stage_report_entry_none_when_absent(tmp_path: Path):
    assert latest_stage_report_entry(tmp_path, "monitor_forward", today_iso="2026-06-16") is None


def test_latest_stage_report_still_returns_bare_report(tmp_path: Path):
    # back-compat: M0/M1 API unchanged
    _write(tmp_path, "monitor_forward", "2026-06-14", "2026-06-14T09:00:00+08:00")
    rep = latest_stage_report(tmp_path, "monitor_forward", today_iso="2026-06-16")
    assert isinstance(rep, StageReport) and rep.stage == "monitor_forward"
