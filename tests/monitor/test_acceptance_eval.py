from __future__ import annotations
import json
from pathlib import Path
from irc.commands import monitor_cmd
from irc.monitor.eval.types import FundTraceBundle
from irc.monitor.render_types import FundView
from irc.monitor.types import (
    MonitorFund, SignalRecord, FactorContribution, NarrativeDoc,
)


def _fund(fid="008986"):
    return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile="gold_etf",
                       themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                       bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)


def _signal(fid):
    return SignalRecord(fund_id=fid, status="ok", bias="ADD_BIAS", composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _stale_view(fid="008986"):
    # NAV older than _NAV_STALE_DAYS (7) → nav_quality FAIL → EVAL_GATED
    return FundView(fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2000-01-02",
                    nav_series=(("2000-01-01", 2.4), ("2000-01-02", 2.5)), signal=_signal(fid),
                    narrative=NarrativeDoc(fid, (), (), (), "ok"), evidence_pool=(),
                    return_table={}, factor_freshness={}, missing_factor_reasons=(),
                    factor_scores=())


class _Cfg:
    class history:
        minimum_observations = 2


def _patch(monkeypatch, funds, views):
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: _Cfg())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: funds)
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda root, today: None)
    # Default: degrade to None so no test reaches the network; override per-test to inject a real calendar.
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda today, root: None)
    # Report v3: run_monitor consumes theme_results at run level (macro narrative).
    # Empty map -> empty macro pool -> gather_macro_narrative early-returns (no LLM).
    monkeypatch.setattr(monitor_cmd, "_build_theme_results", lambda root, funds: {})
    it = iter(views)
    monkeypatch.setattr(monitor_cmd, "_process_fund",
                        lambda fund, cfg, root, llm, **kw: (next(it), [],
                                                             FundTraceBundle(fund.id, (), (), ())))
    monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)


def test_eval_trace_emitted_and_ledger_uses_coalesce_basis(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json").exists()
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert all(r["nav_basis"] == "coalesce(nav_acc,nav)" for r in rows)


def test_trace_carries_missing_trading_days_from_calendar(monkeypatch, tmp_path: Path):
    import datetime as _dt
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    # _stale_view's series is ("2000-01-01"),("2000-01-02") — consecutive, both
    # in a calendar that lists them as trading days → missing_trading_days == 0.
    cal = frozenset({_dt.date(2000, 1, 1), _dt.date(2000, 1, 2)})
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda today, root: cal)
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    assert trace["funds"]["008986"]["nav"]["missing_trading_days"] == 0
    assert trace["schema_version"] == "7"


def test_stale_nav_fund_is_eval_gated_and_panel_names_it(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    f = trace["funds"]["008986"]
    assert f["published_state"] == "EVAL_GATED"
    assert f["validation_badge"] == "gated"
    assert "older than" in f["gate"]["reason"]
    html = (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").read_text(encoding="utf-8")
    # Divergence 1 (spec §5/§8): gate outcome stays visible via the EVAL-GATED badge
    # and the badge tally, NOT via the monitor_signal row status.
    assert "EVAL-GATED" in html and "Validation" in html
    assert "gated: 1" in html
    assert "deterministic_scoring" in html   # the new panel row renders


def test_acceptance_spring_festival_run_day_after_holiday_validates():
    import datetime as _dt
    from irc.monitor.eval.structural import nav_quality
    from irc.monitor.eval.trace import build_eval_trace
    from irc.monitor.eval.types import GateDecision

    # CN Spring-Festival 2026: market closed 2026-02-16..2026-02-20 inclusive.
    # The fund publishes on every trading day around it; the run is dated
    # 2026-02-23 — the FIRST trading day AFTER the holiday (the #158 residual).
    closed = {_dt.date(2026, 2, d) for d in range(16, 21)}
    weekends = {_dt.date(2026, 2, 14), _dt.date(2026, 2, 15),
                _dt.date(2026, 2, 21), _dt.date(2026, 2, 22)}
    cal = frozenset(
        _dt.date(2026, 2, d) for d in range(2, 24)
    ) - closed - weekends
    # NAV series: trading days only, last point is the run date (day after holiday).
    series = tuple((d.isoformat(), 1.0) for d in sorted(cal))

    fund = _fund("008986")
    view = FundView(
        fund_id="008986", name_cn="测试", latest_nav=1.0, as_of_date="2026-02-23",
        nav_series=series, signal=_signal("008986"),
        narrative=NarrativeDoc("008986", (), (), (), "ok"), evidence_pool=(),
        return_table={}, factor_freshness={}, missing_factor_reasons=(), factor_scores=())
    stub = GateDecision("008986", False, (), "validated", "")
    projection = build_eval_trace(
        ((fund, view, stub, FundTraceBundle("008986", (), (), ())),),
        engine_version="1", run_date="2026-02-23", trading_days=cal,
    )["funds"]["008986"]

    assert projection["nav"]["missing_trading_days"] == 0
    # max_gap_days across the closure would be ~9 cal days → the #158 fallback
    # WOULD have WARNed; the calendar branch must validate instead.
    assert projection["nav"]["max_gap_days"] > 8
    health = nav_quality(projection, minimum_observations=2, stale_days=400,
                         today=_dt.date(2026, 2, 23))
    assert health.status == "PASS"


def test_report_header_schema_cannot_drift_from_trace(monkeypatch, tmp_path: Path):
    """RD-1: monitor_cmd's Provenance consumes trace.SCHEMA_VERSION — the report
    header and eval_trace.json move together by construction."""
    from irc.monitor.eval.trace import SCHEMA_VERSION
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    out = tmp_path / "outputs" / "2026-06-16" / "monitor"
    html = (out / "report.html").read_text(encoding="utf-8")
    trace = json.loads((out / "eval_trace.json").read_text(encoding="utf-8"))
    assert f"schema {SCHEMA_VERSION}" in html
    assert trace["schema_version"] == SCHEMA_VERSION == "7"
