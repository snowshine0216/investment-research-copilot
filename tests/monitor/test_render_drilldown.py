from __future__ import annotations
from irc.monitor.holding_metrics import HoldingMetric
from irc.monitor.render_drilldown import holdings_board_html


def _m(symbol, weight, **kw):
    base = dict(pe=None, pb=None, pe_percentile=None, valuation_state=None,
                valuation_reason=None, flow_pct_5d=None, flow_pct_20d=None,
                flow_score=None, flow_reason=None)
    base.update(kw)
    return HoldingMetric(symbol=symbol, name=symbol, weight_pct=weight, **base)


def test_board_renders_present_row_values():
    m = _m("600519", 12.0, pe=30.0, pb=8.0, pe_percentile=0.82,
           valuation_state="expensive", flow_pct_5d=4.0, flow_pct_20d=3.5, flow_score=1.0)
    html = holdings_board_html((m,))
    assert "600519" in html
    assert "30.0" in html and "8.0" in html
    assert "expensive" in html


def test_board_na_cells_show_dash_and_reason():
    m = _m("000001", 5.0, pe=-5.0, valuation_reason="pe_not_positive", flow_reason="flow_no_data")
    html = holdings_board_html((m,))
    assert "—" in html
    assert "pe_not_positive" in html
    assert "flow_no_data" in html


def test_board_rows_sorted_by_weight_desc():
    rows = (_m("aaa", 5.0), _m("bbb", 20.0))
    html = holdings_board_html(rows)
    assert html.index("bbb") < html.index("aaa")


# ── Task 2.3: flow_rollup_html ────────────────────────────────────────────────

from irc.monitor.holding_metrics import FlowAggregate
from irc.monitor.render_drilldown import flow_rollup_html
from irc.monitor.types import SignalRecord, FactorContribution


def _sig(composite=0.3):
    return SignalRecord(fund_id="x", status="ok", bias="ADD_BIAS", composite=composite,
                        signal_confidence=1.0, available_weight=0.9,
                        present_families=("capital-flow",),
                        contributions=(FactorContribution("flow", 0.15, 0.625, 0.094, 1.0, True, ""),),
                        divergence_codes=())


def test_rollup_shows_value_coverage_and_aum_representativeness():
    metrics = (_m("a", 30.0, flow_score=1.0), _m("b", 10.0, flow_score=-0.5))
    agg = FlowAggregate(value=0.625, reason=None, covered_weight_ratio=1.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "0.625" in html or "0.6250" in html
    assert "100%" in html        # covered ratio
    assert "40" in html          # top-5 = 40% of fund AUM (sum of weight_pct)


def test_rollup_na_aggregate_states_reason():
    metrics = (_m("a", 10.0, flow_reason="flow_no_data"),)
    agg = FlowAggregate(value=None, reason="flow_no_coverage", covered_weight_ratio=0.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "flow_no_coverage" in html


def test_rollup_has_no_imperative_trade_language():
    metrics = (_m("a", 30.0, flow_score=1.0),)
    agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    html = flow_rollup_html(metrics, agg, _sig())
    assert "买入" not in html and "卖出" not in html


# ── Task 2.4: drilldown_page_html ────────────────────────────────────────────

from irc.monitor.render_drilldown import drilldown_page_html


def test_drilldown_page_is_self_contained_html_per_fund():
    metrics = (_m("600519", 12.0, pe=30.0, flow_score=1.0),)
    agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    views = (("519069", "易方达蓝筹", metrics, agg, _sig()),)
    html = drilldown_page_html(views)
    assert html.startswith("<!doctype html>")
    assert "519069" in html and "易方达蓝筹" in html
    assert "600519" in html        # board embedded
    assert "<style>" in html       # shared CSS inline (no remote refs)
