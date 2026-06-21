# tests/commands/test_monitor_cmd_valuation.py
from __future__ import annotations

from irc.monitor.types import MonitorFund, NarrativeDoc
from irc.monitor.valuation import ValuationResolution
from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


class _Cfg:
    class history:
        minimum_observations = 2


class _FakeImpacts:
    impacts = ()
    cost_entries = []
    status = "ok"


class _FakeNarr:
    cost_entries = []
    def __init__(self, fid):
        self.doc = NarrativeDoc(fid, (), (), (), "ok")


def _active_fund(fid="110011"):
    return MonitorFund(
        id=fid, name_cn="易方达蓝筹", market="cn_off_exchange",
        analysis_profile="active_cn_equity", themes=("cn_equity_property_policy",),
        constituent_news=True,
        weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50)


def _qdii_fund():
    return MonitorFund(
        id="009225", name_cn="QDII互联网", market="qdii",
        analysis_profile="qdii_china_us_internet", themes=("us_monetary",),
        constituent_news=False,
        weights={"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                 "macro_tilt": 0.20, "constituent": 0.15},
        bands={"buy": 0.40, "sell": -0.40}, minimum_confidence=0.50)


def _snap(fid, holdings):
    return ActiveFundSnapshot(
        fund_id=fid, source_report_date="2026-03-31", source_report_quarter="2026Q1",
        cache_probed_at="2026-06-21T09:00:00",
        constituent_analyses=tuple(
            ConstituentAnalysis(symbol=s, name_cn=n, weight_pct=w,
                                evidence=(), failure_reasons=(), one_line_view="x")
            for s, n, w in holdings),
        failure_reasons_by_symbol={})


def _mature_series_map(*codes):
    from datetime import date
    from irc.opportunity.lookthrough_valuation import MetricSeries
    base = date(2025, 1, 1).toordinal()
    out = {}
    for c in codes:
        pts = tuple((date.fromordinal(base + 2 * i).isoformat(), 40.0 - i * 0.1, 2.0)
                    for i in range(200))  # descending PE → cheap vs own → self>0
        out[c] = MetricSeries(code=c, source="eastmoney", points=pts)
    return out


def _patch_common(monkeypatch, mc):
    monkeypatch.setattr(mc, "nav_series_for", lambda _fid: None)
    monkeypatch.setattr(mc, "build_evidence_pool", lambda fund, repo_root: ())
    monkeypatch.setattr(mc, "gather_impacts", lambda **_kw: _FakeImpacts())
    monkeypatch.setattr(mc, "build_constituent_pool", lambda fid, root: ())
    monkeypatch.setattr(mc, "heat_inputs_for", lambda fid, purchase_table: (None, None))
    monkeypatch.setattr(mc, "fetch_flow_series", lambda symbols, cache_dir, today: {})
    # industry edge fetchers — injected to avoid network
    monkeypatch.setattr(mc, "fetch_industry_pe",
                        lambda cache_dir, today: {"酿酒行业": 60.0})
    monkeypatch.setattr(mc, "fetch_stock_industry_map",
                        lambda symbols, cache_dir, today: {s: "酿酒行业" for s in symbols})


def test_lookthrough_active_fund_gets_eligible_bottomup_valuation(monkeypatch, tmp_path):
    """(a) A look-through active fund with A-share holdings gets a bottom-up
    valuation FactorScore (eligible) end-to-end via the REAL _process_fund."""
    import irc.commands.monitor_cmd as mc
    import irc.opportunity.inputs_loader as il
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("110011"))
    monkeypatch.setattr(mc, "load_latest_active_fund_cached",
                        lambda fid, data_dir: _snap("110011", [("600519", "茅台", 60.0)]))
    # look-through path (no tracked_index)
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, None, path="lookthrough"))
    monkeypatch.setattr(il, "_stock_series_by_code",
                        lambda con, syms: _mature_series_map(*syms))

    view, _c, _b = mc._process_fund(_active_fund(), _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is True, f"valuation must be eligible; reason={val.reason!r}"
    assert val.value is not None


def test_qdii_009225_stays_valuation_no_anchor_via_state_path(monkeypatch, tmp_path):
    """(b) 009225 lookthrough path but NO holding_metrics (fund_level profile
    builds none) → valuation_aggregate stays None → state path → valuation_no_anchor."""
    import irc.commands.monitor_cmd as mc
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("009225"))
    # qdii_china_us_internet profile.lookthrough == "fund_level" → NO active_fund
    # holdings branch → holding_metrics empty.
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: None)
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution(None, False, "valuation_no_anchor", path="lookthrough"))

    view, _c, _b = mc._process_fund(_qdii_fund(), _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is False
    assert val.reason == "valuation_no_anchor"


def test_synthetic_index_path_fund_rides_index_state(monkeypatch, tmp_path):
    """(c) A SYNTHETIC index-path fixture fund rides the index state — NOT 018132
    (look-through in prod). path=="index" → valuation_aggregate stays None → state."""
    import irc.commands.monitor_cmd as mc
    import irc.opportunity.inputs_loader as il
    _patch_common(monkeypatch, mc)
    monkeypatch.setattr(mc, "gather_narrative", lambda **_kw: _FakeNarr("510300"))
    monkeypatch.setattr(mc, "load_latest_active_fund_cached", lambda fid, data_dir: None)
    monkeypatch.setattr(il, "_stock_series_by_code", lambda con, syms: {})
    # index path resolves a real state
    monkeypatch.setattr(mc, "resolve_valuation_state",
                        lambda fund, con, root: ValuationResolution("cheap", True, None, path="index"))

    fund = _active_fund("510300")
    view, _c, _b = mc._process_fund(fund, _Cfg(), tmp_path, object(),
                                    con=object(), today="2026-06-21")
    val = [s for s in view.factor_scores if s.name == "valuation"][0]
    assert val.eligible is True
    assert val.value == 1.0  # "cheap" → +1.0 via the state path (NOT the aggregate)
