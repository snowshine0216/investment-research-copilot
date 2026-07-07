"""Tests for the `monitor` run-kind in the notify pipeline.

Success detection: a monitor run succeeds iff `outputs/<date>/monitor/monitor.json`
exists. `monitor.json` is the LAST of the five atomic writes in
`monitor_cmd._write_outputs` (report.html → signal.json → impacts.json →
narrative.json → monitor.json), so its presence is the only artifact that proves
the whole output set was written. A crash after report.html but before
monitor.json leaves a present-but-incomplete set; keying on report.html would
mis-report that partial run as success.
"""
from __future__ import annotations

from pathlib import Path

from irc.commands.notify_cmd import _build_outcome, _china_today
from irc.notify.classify import classify_run_outcome


def _monitor_dir(tmp_path: Path) -> Path:
    out = tmp_path / "outputs" / _china_today().isoformat() / "monitor"
    out.mkdir(parents=True)
    return out


def test_monitor_success_when_monitor_json_present(tmp_path: Path) -> None:
    out = _monitor_dir(tmp_path)
    (out / "monitor.json").write_text("{}", encoding="utf-8")
    # Task 8: _build_outcome now attaches a health digest for run_kind="monitor",
    # read from these two companion artifacts. A truly-absent eval_trace.json /
    # fund_flow_series.json is health_unknown (warn) by design (spec AC5), which
    # would escalate this test's assertion away from "clean" — so seed a
    # trivially-healthy (empty) shape for both, isolating this test to its own
    # concern (the monitor.json sentinel, not health gathering).
    (out / "eval_trace.json").write_text(
        '{"board_pe_freshness": {"state": "FRESH"}, "funds": {}}', encoding="utf-8"
    )
    dd = tmp_path / "data" / "monitor"
    dd.mkdir(parents=True)
    (dd / "fund_flow_series.json").write_text("{}", encoding="utf-8")
    outcome = _build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "clean"


def test_monitor_failed_when_monitor_json_absent(tmp_path: Path) -> None:
    _monitor_dir(tmp_path)
    outcome = _build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "failed"


def test_monitor_failed_on_partial_output_report_without_monitor_json(
    tmp_path: Path,
) -> None:
    """Regression: report.html present but monitor.json absent (crash mid-write)
    must NOT be classified as success."""
    out = _monitor_dir(tmp_path)
    (out / "report.html").write_text("<html></html>", encoding="utf-8")
    outcome = _build_outcome(tmp_path, run_kind="monitor", last_exit_code=0)
    decision = classify_run_outcome(outcome, notify_on_clean=True)
    assert decision.severity == "failed"
