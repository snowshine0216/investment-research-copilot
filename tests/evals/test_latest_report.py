from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from evals._shared.latest_report import latest_stage_report
from evals._shared.report_schema import StageReport, report_to_dict
from irc.monitor.eval.staleness import resolve_health

_TZ = timezone(timedelta(hours=8))


def _write(root: Path, stage: str, date_str: str, overall: str = "PASS") -> None:
    d = root / "outputs" / date_str / "evals" / stage
    d.mkdir(parents=True)
    rep = StageReport(stage=stage, ran_at=f"{date_str}T09:00:00+08:00",
                      based_on=[], metrics=[], overall=overall)
    (d / "report.json").write_text(json.dumps(report_to_dict(rep)), encoding="utf-8")


def test_absent_returns_none(tmp_path: Path):
    assert latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16") is None


def test_multiple_dates_returns_newest(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-10", overall="FAIL")
    _write(tmp_path, "monitor_impact", "2026-06-14", overall="PASS")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.ran_at.startswith("2026-06-14")
    assert rep.overall == "PASS"


def test_ignores_dates_after_today(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-14", overall="PASS")
    _write(tmp_path, "monitor_impact", "2026-06-20", overall="FAIL")  # future
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.ran_at.startswith("2026-06-14")


def test_today_present_returns_today(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-16", overall="WARN")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.overall == "WARN"


def test_skipped_today_resolves_to_unknown(tmp_path: Path):
    _write(tmp_path, "monitor_impact", "2026-06-16", overall="SKIPPED")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    now = datetime(2026, 6, 16, 12, tzinfo=_TZ)
    h = resolve_health(rep, now=now, stale_after_days=14)
    assert h.status == "UNKNOWN" and "skipped" in h.reasons[0]


def test_corrupt_newest_report_is_skipped_falls_through_to_next_valid(tmp_path: Path):
    # Newest date has a truncated/corrupt report.json → should skip it, not raise
    corrupt_dir = tmp_path / "outputs" / "2026-06-16" / "evals" / "monitor_impact"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "report.json").write_text("{bad json}", encoding="utf-8")
    # Older date is valid
    _write(tmp_path, "monitor_impact", "2026-06-14", overall="PASS")
    rep = latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16")
    assert rep is not None and rep.overall == "PASS"


def test_all_corrupt_reports_returns_none(tmp_path: Path):
    for d in ("2026-06-14", "2026-06-15"):
        corrupt_dir = tmp_path / "outputs" / d / "evals" / "monitor_impact"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "report.json").write_text("{bad}", encoding="utf-8")
    assert latest_stage_report(tmp_path, "monitor_impact", today_iso="2026-06-16") is None
