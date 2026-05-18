"""Report-path helper tests.

Spec: docs/superpowers/specs/2026-05-18-eval-truthfulness-and-green-suite-design.md
Item: AUTODEV-LOOP/items/004-spec.md
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from evals._shared.report_paths import report_dir, write_report
from evals._shared.report_schema import StageReport


def _report(stage: str = "demo") -> StageReport:
    return StageReport(
        stage=stage,
        ran_at="2026-05-18T08:00:00+08:00",
        based_on=["src"],
        metrics=[],
        overall="PASS",
    )


def test_report_dir_under_artifact_date(tmp_path: Path) -> None:
    expected = tmp_path / "outputs" / "2026-05-17" / "evals" / "demo"
    assert report_dir(tmp_path, "demo", "2026-05-17") == expected


def test_write_report_creates_parents_and_returns_path(tmp_path: Path) -> None:
    path = write_report(tmp_path, _report(), artifact_date="2026-05-17")
    assert path == tmp_path / "outputs" / "2026-05-17" / "evals" / "demo" / "report.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["stage"] == "demo"
    assert body["overall"] == "PASS"


def test_write_report_overwrites_existing(tmp_path: Path) -> None:
    first = write_report(tmp_path, _report(), artifact_date="2026-05-17")
    first.write_text("stale", encoding="utf-8")
    write_report(tmp_path, _report(), artifact_date="2026-05-17")
    body = json.loads(first.read_text(encoding="utf-8"))
    assert body["stage"] == "demo"


def test_write_missing_input_report_still_lands_under_run_date(
    tmp_path: Path, monkeypatch,
) -> None:
    """`write_missing_input_report` keeps its run-date default behavior."""
    from evals._shared import missing_input

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz):
            return datetime(2099, 1, 2, tzinfo=timezone(timedelta(hours=8)))

    monkeypatch.setattr(missing_input, "datetime", _FrozenDatetime)
    rep = missing_input.missing_input_report(
        stage="demo", reason="absent", based_on_path="some/path",
    )
    path = missing_input.write_missing_input_report(tmp_path, rep)
    assert path.parent == tmp_path / "outputs" / "2099-01-02" / "evals" / "demo"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["overall"] == "FAIL"


def test_write_missing_input_report_accepts_explicit_date(tmp_path: Path) -> None:
    from evals._shared import missing_input

    rep = missing_input.missing_input_report(
        stage="demo", reason="absent", based_on_path=None,
    )
    path = missing_input.write_missing_input_report(tmp_path, rep, date_str="2026-04-01")
    assert path.parent == tmp_path / "outputs" / "2026-04-01" / "evals" / "demo"
