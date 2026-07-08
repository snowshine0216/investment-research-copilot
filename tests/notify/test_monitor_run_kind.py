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

import json
from pathlib import Path

from irc.commands.notify_cmd import _build_outcome, _china_today
from irc.notify.classify import classify_run_outcome


def _monitor_dir(tmp_path: Path) -> Path:
    out = tmp_path / "outputs" / _china_today().isoformat() / "monitor"
    out.mkdir(parents=True)
    return out


def _write_healthy_trace(out: Path) -> None:
    """A FRESH board-PE trace with no funds — `monitor_health` sees this as
    clean (no items), so it doesn't interact with severity in tests that
    aren't about health. Task 4 wired `_build_outcome` to always attach
    `read_monitor_health` for `run_kind == "monitor"`; a bare `monitor.json`
    with no `eval_trace.json` at all now reads as `health_unknown` (warn) —
    correctly so, since a real run's `_write_eval_artifacts` best-effort-writes
    `eval_trace.json` and its absence is itself a genuine degrade signal. This
    "success" fixture must model a fully-healthy artifact set to keep testing
    only the `monitor.json` sentinel logic, not health escalation."""
    (out / "eval_trace.json").write_text(
        json.dumps({"board_pe_freshness": {"state": "FRESH", "as_of": "2026-07-07", "age_td": 0}}),
        encoding="utf-8",
    )


def _write_healthy_flow(tmp_path: Path) -> None:
    """A present-but-empty flow store: valid JSON (not missing/corrupt), so it
    doesn't trip the P0-2 absent-store health_unknown warning, and empty
    (no symbols), so it doesn't trip flow_stale/flow_symbol_stale either —
    needed to keep this fixture genuinely "fully healthy" per Finding 2."""
    data_dir = tmp_path / "data" / "monitor"
    data_dir.mkdir(parents=True)
    (data_dir / "fund_flow_series.json").write_text("{}", encoding="utf-8")


def test_monitor_success_when_monitor_json_present(tmp_path: Path) -> None:
    out = _monitor_dir(tmp_path)
    (out / "monitor.json").write_text("{}", encoding="utf-8")
    _write_healthy_trace(out)
    _write_healthy_flow(tmp_path)
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
