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


def _signal(fid, status="ok", bias="ADD_BIAS"):
    return SignalRecord(fund_id=fid, status=status, bias=bias, composite=0.3,
                        signal_confidence=1.0, available_weight=1.0,
                        present_families=("price-momentum",),
                        contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
                        divergence_codes=())


def _view(fid, *, degraded=False):
    series = () if degraded else (("2026-06-15", 2.4), ("2026-06-16", 2.5))
    return FundView(fund_id=fid, name_cn="测试", latest_nav=0.0 if degraded else 2.0,
                    as_of_date="N/A" if degraded else "2026-06-16", nav_series=series,
                    signal=_signal(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
                    evidence_pool=(), return_table={}, factor_freshness={},
                    missing_factor_reasons=(), factor_scores=())


class _Cfg:
    class history:
        minimum_observations = 2


def _patch_pipeline(monkeypatch, funds, views):
    monkeypatch.setattr(monitor_cmd, "load_monitor_config", lambda root: _Cfg())
    monkeypatch.setattr(monitor_cmd, "resolve_funds", lambda cfg: funds)
    monkeypatch.setattr(monitor_cmd, "load_yaml", lambda *a, **k: object())
    monkeypatch.setattr(monitor_cmd, "preflight_gate", lambda *a, **k: 0)
    monkeypatch.setattr(monitor_cmd, "record_command_run", lambda **k: None)
    monkeypatch.setattr(monitor_cmd, "_read_prior_signal", lambda root, today: None)
    monkeypatch.setattr(monitor_cmd, "load_trading_days", lambda today, root: None)
    # Report v3: run_monitor consumes theme_results at run level (macro narrative).
    # Empty map -> empty macro pool -> gather_macro_narrative early-returns (no LLM).
    monkeypatch.setattr(monitor_cmd, "_build_theme_results", lambda root, funds: {})
    view_iter = iter(views)
    monkeypatch.setattr(
        monitor_cmd, "_process_fund",
        lambda fund, cfg, root, llm, **kw: (next(view_iter), [],
                                             FundTraceBundle(fund.id, (), (), ())),
    )
    monkeypatch.setattr(monitor_cmd, "fetch_purchase_table", lambda: None)


def test_run_monitor_writes_eval_trace_and_ledger(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch_pipeline(monkeypatch, funds, [_view("008986")])
    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    trace_path = tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "008986" in trace["funds"]
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    assert ledger.exists()
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[0]["nav_basis"] == "coalesce(nav_acc,nav)"


def test_degraded_nav_fund_is_eval_gated_with_null_nav_acc(monkeypatch, tmp_path: Path):
    funds = [_fund("600000")]
    _patch_pipeline(monkeypatch, funds, [_view("600000", degraded=True)])
    monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    trace = json.loads(
        (tmp_path / "outputs" / "2026-06-16" / "monitor" / "eval_trace.json")
        .read_text(encoding="utf-8"))
    assert trace["funds"]["600000"]["published_state"] == "EVAL_GATED"
    rows = [json.loads(line) for line in
            (tmp_path / "data" / "monitor" / "forward_ledger.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert rows[0]["nav_acc"] is None


def test_compute_gates_degrades_to_fail_on_recompute_error(monkeypatch, tmp_path: Path):
    """Finding C: a per-fund error inside deterministic_health must not crash
    _compute_gates.  The offending fund degrades to FAIL with a recompute_error
    reason; the run still completes."""
    funds = [_fund("008986"), _fund("159934")]
    _patch_pipeline(monkeypatch, funds, [_view("008986"), _view("159934")])

    # Patch build_eval_trace so the projection for 159934 lacks 'signal'.
    real_build_eval_trace = monitor_cmd.build_eval_trace

    def patched_build_eval_trace(items, *, engine_version, run_date, trading_days=None):
        result = real_build_eval_trace(
            items, engine_version=engine_version, run_date=run_date, trading_days=trading_days,
        )
        # Remove 'resolved' from 159934's projection to trigger a KeyError in
        # deterministic_health (recompute_signal_from_trace reads trace_fund["resolved"]).
        # monitor_signal_health does NOT read 'resolved', so only deterministic_health
        # raises — which is the error boundary we are hardening.
        if "159934" in result.get("funds", {}):
            result["funds"]["159934"].pop("resolved", None)
        return result

    monkeypatch.setattr(monitor_cmd, "build_eval_trace", patched_build_eval_trace)

    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0


def test_run_monitor_still_renders_when_trace_write_fails(monkeypatch, tmp_path: Path):
    funds = [_fund("008986")]
    _patch_pipeline(monkeypatch, funds, [_view("008986")])

    real_write = monitor_cmd.atomic_write_text

    def flaky_write(path, content, *a, **k):
        if path.name == "eval_trace.json":
            raise OSError("disk full")
        return real_write(path, content, *a, **k)

    monkeypatch.setattr(monitor_cmd, "atomic_write_text", flaky_write)
    rc = monitor_cmd.run_monitor(repo_root=str(tmp_path), today="2026-06-16")
    assert rc == 0
    assert (tmp_path / "outputs" / "2026-06-16" / "monitor" / "report.html").exists()


def test_valuation_health_exception_fallback_is_warn(monkeypatch, tmp_path: Path):
    """Task 4.2: a per-fund exception in valuation_reconciliation must not crash
    _compute_gates — degrades to WARN, run still completes."""
    import irc.commands.monitor_cmd as mc

    def _local_fund(fid="008986"):
        return MonitorFund(id=fid, name_cn="测试", market="CN", analysis_profile="gold_etf",
                           themes=("gold",), constituent_news=False, weights={"trend": 1.0},
                           bands={"buy": 0.1, "sell": -0.1}, minimum_confidence=0.5)

    def _local_view(fid):
        return FundView(
            fund_id=fid, name_cn="x", latest_nav=2.0, as_of_date="2026-06-21",
            nav_series=(("2026-06-18", 2.4), ("2026-06-19", 2.5)),
            signal=_signal(fid), narrative=NarrativeDoc(fid, (), (), (), "ok"),
            evidence_pool=(), return_table={}, factor_freshness={},
            missing_factor_reasons=(), factor_scores=(),
        )

    fund = _local_fund()
    view = _local_view(fund.id)
    bundle = FundTraceBundle(fund.id, (), (), ())

    def _boom(_proj):
        raise RuntimeError("boom")

    monkeypatch.setattr(mc, "valuation_reconciliation", _boom)
    result = mc._compute_gates(
        [fund], [view], [bundle], min_obs=2, suite_healths=(), trading_days=None,
    )
    # _compute_gates now returns 7-tuple:
    # (gates, signal_h, det_h, flow_recon_h, flow_cov_h, val_recon_h, val_cov_h)
    val_recon = result[5]
    assert val_recon[fund.id].status == "WARN"


def test_ledger_row_carries_market_composite(tmp_path):
    """_write_eval_artifacts ledger rows include market_composite from view.market_view."""
    import json
    from irc.monitor.market_composite import MarketCompositeView
    import dataclasses
    from irc.monitor.eval.types import GateDecision, FundTraceBundle
    from irc.commands.monitor_cmd import _write_eval_artifacts

    fund = _fund("519069")
    mv = MarketCompositeView(composite=0.55, bias="ADD_BIAS", news_delta=0.10,
                             eligible_market_factors=3)
    view = dataclasses.replace(_view("519069"), market_view=mv)
    gate = GateDecision("519069", False, (), "validated", "")
    bundle = FundTraceBundle("519069", (), (), ())
    out = tmp_path / "monitor"
    out.mkdir()
    _write_eval_artifacts(out, tmp_path, [fund], [view], [bundle], (gate,),
                          run_date="2026-06-30", trading_days=None)
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["market_composite"] == 0.55
    assert rows[0]["market_bias"] == "ADD_BIAS"


def test_ledger_row_market_composite_none_when_no_market_view(tmp_path):
    """View without market_view → market_composite/market_bias are None in ledger."""
    import json
    from irc.monitor.eval.types import GateDecision, FundTraceBundle
    from irc.commands.monitor_cmd import _write_eval_artifacts

    fund = _fund("519069")
    view = _view("519069")   # market_view=None by default
    gate = GateDecision("519069", False, (), "validated", "")
    bundle = FundTraceBundle("519069", (), (), ())
    out = tmp_path / "monitor"
    out.mkdir()
    _write_eval_artifacts(out, tmp_path, [fund], [view], [bundle], (gate,),
                          run_date="2026-06-30", trading_days=None)
    ledger = tmp_path / "data" / "monitor" / "forward_ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert rows[0]["market_composite"] is None
    assert rows[0]["market_bias"] is None
