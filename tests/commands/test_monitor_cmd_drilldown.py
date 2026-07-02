from __future__ import annotations
from pathlib import Path
from irc.monitor.holding_metrics import build_holding_metrics, HoldingMetric
from irc.monitor.types import MonitorFund, SignalRecord, FactorContribution, NarrativeDoc
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


def test_build_holding_metrics_assembles_from_loaded_inputs():
    # Pure assembly helper — NO I/O. Top holdings + pre-loaded series in → metrics out.
    class _H:
        def __init__(self, s, n, w):
            self.symbol, self.name_cn, self.weight_pct = s, n, w
    holdings = (_H("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": (("2026-06-16", 4.0),) * 20}
    metrics = build_holding_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    assert isinstance(metrics[0], HoldingMetric)
    assert metrics[0].flow_score == 1.0


# ── Finding 1: flow aggregate wired into FactorInputs for active_cn_equity ───

class _Cfg:
    class history:
        minimum_observations = 2


def _active_fund():
    return MonitorFund(
        id="110011",
        name_cn="易方达蓝筹",
        market="cn_off_exchange",
        analysis_profile="active_cn_equity",
        themes=("cn_equity_property_policy",),
        constituent_news=True,
        weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40},
        minimum_confidence=0.50,
    )


def _fake_snap():
    """ActiveFundSnapshot with 2 holdings (> 0.50 total weight → coverage gate passes)."""
    def _ca(symbol, name, weight):
        return ConstituentAnalysis(
            symbol=symbol, name_cn=name, weight_pct=weight,
            evidence=(), failure_reasons=(), one_line_view="stub",
        )
    return ActiveFundSnapshot(
        fund_id="110011",
        source_report_date="2026-03-31",
        source_report_quarter="2026Q1",
        cache_probed_at="2026-06-19T09:00:00",
        constituent_analyses=(
            _ca("600519", "贵州茅台", 35.0),
            _ca("000858", "五粮液", 25.0),
        ),
        failure_reasons_by_symbol={},
    )


def _flow_series_with_coverage():
    """20 daily flow rows for each symbol — enough for coverage >= 0.50."""
    rows = tuple(("2026-06-" + str(i).zfill(2), 3.5) for i in range(1, 21))
    return {
        "600519": rows,
        "000858": rows,
    }


def test_flow_wired_into_composite_for_active_cn_equity(monkeypatch, tmp_path: Path):
    """FINDING 1 (RED): flow aggregate must be passed to FactorInputs for active_cn_equity.
    Before the fix, FactorInputs.flow is None → _flow() returns 'flow_no_data' →
    FactorScore(eligible=False). After the fix, eligible=True and value is non-None."""
    import irc.commands.monitor_cmd as mc

    monkeypatch.setattr(mc, "nav_series_for", lambda _fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, **k: ())
    monkeypatch.setattr(mc, "gather_impacts", lambda **_kw: _FakeImpacts())
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr())
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: _fake_snap())
    monkeypatch.setattr(mc, "_load_flow_store_slice",
                        lambda root, symbols: _flow_series_with_coverage())
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, "valuation_no_anchor"))
    monkeypatch.setattr(mc, "heat_inputs_for", lambda fid, purchase_table: (None, None))
    # _stock_series_by_code is imported inside _process_fund from irc.opportunity.inputs_loader
    import irc.opportunity.inputs_loader as il
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})

    fund = _active_fund()
    cfg = _Cfg()
    llm_config = object()

    view, _costs, _bundle = mc._process_fund(
        fund, cfg, tmp_path, llm_config, today="2026-06-19",
    )

    flow_scores = [s for s in view.factor_scores if s.name == "flow"]
    assert flow_scores, "No flow FactorScore returned"
    fs = flow_scores[0]
    assert fs.eligible, (
        f"flow factor should be eligible (value present), got eligible={fs.eligible}, "
        f"reason={fs.reason!r}"
    )
    assert fs.value is not None, "flow factor value should be non-None"


class _FakeImpacts:
    impacts = ()
    cost_entries = []
    status = "ok"

    def _impact_rows_from(self, fund):
        return ()


class _FakeNarr:
    doc = NarrativeDoc("110011", (), (), (), "ok")
    cost_entries = []


# ── Finding 2: exception in flow_reconciliation must yield WARN, not PASS ─────

def test_flow_health_exception_fallback_is_warn(monkeypatch, tmp_path: Path):
    """FINDING 2 (RED): when flow_reconciliation raises, the fallback StageHealth
    must have status='WARN', not 'PASS' (the current bug)."""
    import irc.commands.monitor_cmd as mc
    from irc.monitor.eval.types import FundTraceBundle

    def _signal(fid):
        return SignalRecord(
            fund_id=fid, status="ok", bias="ADD_BIAS", composite=0.3,
            signal_confidence=1.0, available_weight=1.0,
            present_families=("price-momentum",),
            contributions=(FactorContribution("trend", 1.0, 0.3, 0.3, 1.0, True, ""),),
            divergence_codes=(),
        )

    from irc.monitor.render_types import FundView

    def _view(fid):
        return FundView(
            fund_id=fid, name_cn="测试", latest_nav=2.0, as_of_date="2026-06-19",
            nav_series=(("2026-06-18", 2.4), ("2026-06-19", 2.5)),
            signal=_signal(fid),
            narrative=NarrativeDoc(fid, (), (), (), "ok"),
            evidence_pool=(), return_table={}, factor_freshness={},
            missing_factor_reasons=(), factor_scores=(),
        )

    fund = _active_fund()
    view = _view(fund.id)
    bundle = FundTraceBundle(fund.id, (), (), ())

    # Patch flow_reconciliation to raise
    def _boom(_proj):
        raise RuntimeError("boom")
    monkeypatch.setattr(mc, "flow_reconciliation", _boom)

    _, _sh, _dh, flow_recon_healths, _fch, _vrh, _vch = mc._compute_gates(
        [fund], [view], [bundle],
        min_obs=2, suite_healths=(),
        trading_days=None,
    )

    health = flow_recon_healths.get(fund.id)
    assert health is not None, "No flow_recon_health returned for fund"
    assert health.status == "WARN", (
        f"Expected WARN on exception fallback, got status={health.status!r}. "
        f"Reasons: {health.reasons}"
    )
