"""Tests for the `monitor` run-kind in the notify pipeline.

Success detection: a monitor run succeeds iff
`outputs/<date>/monitor/report.html` exists (not decision_report.json).
"""
from __future__ import annotations

from pathlib import Path

from irc.commands.notify_cmd import _build_outcome, _china_today
from irc.notify.classify import classify_run_outcome


def _setup(tmp_path: Path, *, with_report: bool) -> None:
    out = tmp_path / "outputs" / _china_today().isoformat() / "monitor"
    out.mkdir(parents=True)
    if with_report:
        (out / "report.html").write_text("<html></html>", encoding="utf-8")


def test_monitor_success_when_report_present(tmp_path: Path) -> None:
    _setup(tmp_path, with_report=True)
    outcome = _build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "clean"


def test_monitor_failed_when_report_absent(tmp_path: Path) -> None:
    _setup(tmp_path, with_report=False)
    outcome = _build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "failed"
