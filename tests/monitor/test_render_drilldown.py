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
