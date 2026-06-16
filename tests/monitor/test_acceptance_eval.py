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
    it = iter(views)
    monkeypatch.setattr(monitor_cmd, "_process_fund",
                        lambda fund, cfg, root, llm: (next(it), [],
                                                      FundTraceBundle(fund.id, (), (), ())))


def test_eval_trace_emitted_and_ledger_uses_coalesce_basis(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch(monkeypatch, funds, [_stale_view("008986")])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json").exists()
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert all(r["nav_basis"] == "coalesce(nav_acc,nav)" for r in rows)


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
