from __future__ import annotations
import json
from pathlib import Path
from datetime import date, timedelta
import irc.commands.monitor_cmd as monitor_cmd
from irc.commands.monitor_cmd import _append_nav_history_for_views, _write_eval_artifacts
from irc.monitor.render_types import FundView
from irc.monitor.types import NarrativeDoc, SignalRecord


def _sig():
    return SignalRecord(fund_id="a", status="ok", bias="ADD_BIAS", composite=0.2,
                        signal_confidence=0.9, available_weight=1.0, present_families=(),
                        contributions=(), divergence_codes=())


def _view(fund_id, series):
    return FundView(fund_id=fund_id, name_cn="x", latest_nav=1.0,
                    as_of_date=series[-1][0] if series else "N/A", nav_series=series,
                    signal=_sig(), narrative=NarrativeDoc(fund_id, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=())


def test_append_bounded_tail_only(tmp_path: Path):
    d0 = date.fromisoformat("2026-01-01")
    series = tuple(((d0 + timedelta(days=i)).isoformat(), 1.0 + 0.001 * i) for i in range(120))
    run_date = (d0 + timedelta(days=119)).isoformat()
    views = [_view("a", series)]
    _append_nav_history_for_views(tmp_path, views, run_date=run_date, written_at="w")
    p = tmp_path / "data" / "monitor" / "nav_history.jsonl"
    rows = [json.loads(ln) for ln in p.read_text().splitlines()]
    cutoff = (date.fromisoformat(run_date) - timedelta(days=60)).isoformat()
    assert rows, "no rows appended"
    assert all(r["nav_date"] >= cutoff for r in rows)
    assert len(rows) < 120                       # bounded, not the full series
    assert all(r["source_run_date"] == run_date for r in rows)


def test_append_never_crashes_on_empty_series(tmp_path: Path):
    _append_nav_history_for_views(tmp_path, [_view("a", ())], run_date="2026-01-01",
                                  written_at="w")  # no exception


def test_eval_artifacts_completes_when_now_iso_raises(tmp_path: Path, monkeypatch):
    """Regression (PR #140 latent bug): if _now_iso raises, written_at must still be
    bound so the trailing nav-history append cannot crash the brief with a NameError."""
    def _boom() -> str:
        raise RuntimeError("clock unavailable")

    monkeypatch.setattr(monitor_cmd, "_now_iso", _boom)
    _write_eval_artifacts(  # must not raise — the brief still renders
        tmp_path, tmp_path, [], [], [], (), run_date="2026-01-01", trading_days=None,
    )
