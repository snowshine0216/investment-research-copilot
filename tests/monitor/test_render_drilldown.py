from __future__ import annotations

from irc.monitor.holding_metrics import FlowAggregate, HoldingMetric, ValuationAggregate
from irc.monitor.render_drilldown import (
    drilldown_page_html,
    flow_rollup_html,
    holdings_board_html,
)
from irc.monitor.types import FactorContribution, SignalRecord


def _m(symbol, weight, **kw):
    base = dict(pe=None, pb=None, pe_percentile=None, valuation_state=None,
                valuation_reason=None, flow_pct_5d=None, flow_pct_20d=None,
                flow_score=None, flow_reason=None,
                self_score=None, industry=None, industry_pe=None,
                industry_richness=None, industry_score=None, val_score=None,
                false_cheap=False, industry_reason=None)
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


def test_drilldown_page_is_self_contained_html_per_fund():
    metrics = (_m("600519", 12.0, pe=30.0, flow_score=1.0),)
    agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    views = (("519069", "易方达蓝筹", metrics, agg, _sig()),)
    html = drilldown_page_html(views)
    assert html.startswith("<!doctype html>")
    assert "519069" in html and "易方达蓝筹" in html
    assert "600519" in html        # board embedded
    assert "<style>" in html       # shared CSS inline (no remote refs)


# ── Slice 3: industry columns + value-trap badge + valuation rollup ───────────


def test_board_renders_industry_columns():
    m = _m("600519", 12.0, pe=30.0, pb=8.0, pe_percentile=0.82,
           valuation_state="cheap", self_score=1.0, industry="酿酒行业",
           industry_pe=20.0, industry_richness=1.5, industry_score=-1.0,
           val_score=0.0, false_cheap=True, industry_reason="false_cheap_clamp")
    html = holdings_board_html((m,))
    assert "酿酒行业" in html        # 行业 column
    assert "20.0" in html            # 行业PE
    assert "1.5" in html or "1.50" in html  # r
    assert "中性" in html            # value-trap badge annotation


def test_board_value_trap_badge_only_on_clamped_rows():
    clean = _m("000858", 8.0, val_score=0.5, false_cheap=False)
    html = holdings_board_html((clean,))
    assert "价值陷阱" not in html     # no badge on a non-clamped row


def test_valuation_rollup_always_shows_industry_coverage():
    from irc.monitor.render_drilldown import valuation_rollup_html
    metrics = (_m("a", 60.0, val_score=1.0, industry="X", industry_score=1.0),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "行业覆盖" in html


def test_valuation_rollup_sub_50_industry_coverage_note():
    from irc.monitor.render_drilldown import valuation_rollup_html
    # one covered row WITHOUT an industry leg → industry coverage 0% < 0.50 → note.
    metrics = (_m("a", 60.0, val_score=1.0, industry=None, industry_score=None),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "价值陷阱检测数据有限" in html or "不可用" in html


def test_valuation_rollup_no_imperative_language():
    from irc.monitor.render_drilldown import valuation_rollup_html
    metrics = (_m("a", 60.0, val_score=1.0, industry="X", industry_score=1.0),)
    agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.60)
    html = valuation_rollup_html(metrics, agg)
    assert "买入" not in html and "卖出" not in html


# ── Slice 3 followup: valuation rollup wired into drilldown_page_html ─────────


def test_drilldown_page_renders_valuation_rollup_for_lookthrough_fund():
    """§5.D: drilldown_page_html must render valuation rollup (行业覆盖) for a
    look-through fund whose val_agg is provided as the 6th tuple element."""
    metrics = (_m("600519", 35.0, val_score=1.0, industry="酿酒行业", industry_score=1.0),)
    flow_agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    val_agg = ValuationAggregate(value=1.0, reason=None, covered_weight_ratio=0.35)
    views = (("519069", "易方达蓝筹", metrics, flow_agg, _sig(), val_agg),)
    html = drilldown_page_html(views)
    assert "行业覆盖" in html


def test_drilldown_page_sub50_industry_coverage_note_in_rendered_page():
    """§6/Q7: when covered rows have NO industry leg (coverage 0% < 0.50),
    the sub-0.50 note fires inside the rendered drilldown page."""
    # covered by val_score but NO industry leg — coverage = 0% < 0.50
    metrics = (_m("000858", 30.0, val_score=1.0, industry=None, industry_score=None),)
    flow_agg = FlowAggregate(value=None, reason="flow_no_data", covered_weight_ratio=0.0)
    val_agg = ValuationAggregate(value=0.5, reason=None, covered_weight_ratio=0.30)
    views = (("000858", "五粮液", metrics, flow_agg, _sig(), val_agg),)
    html = drilldown_page_html(views)
    assert "价值陷阱检测数据有限" in html or "不可用" in html


def test_drilldown_page_legacy_5tuple_still_works():
    """Backward-compat: existing 5-tuple callers (val_agg absent) must not break."""
    metrics = (_m("600519", 12.0, pe=30.0, flow_score=1.0),)
    flow_agg = FlowAggregate(value=1.0, reason=None, covered_weight_ratio=1.0)
    views = (("519069", "易方达蓝筹", metrics, flow_agg, _sig()),)
    html = drilldown_page_html(views)
    assert "519069" in html
    assert html.startswith("<!doctype html>")


# ── Phase 6: 盘中提示 provisional flow annotation ───────────────────────────────


def test_provisional_flow_annotation_renders_intraday_note():
    from irc.monitor.render_drilldown import provisional_flow_annotation_html

    html = provisional_flow_annotation_html(symbol_value=2.3, as_of_hhmm="12:15")
    assert "盘中主力净流入" in html
    assert "12:15" in html
    assert "盘中值，非因子输入" in html


def test_provisional_flow_annotation_none_value_renders_empty():
    from irc.monitor.render_drilldown import provisional_flow_annotation_html
    assert provisional_flow_annotation_html(symbol_value=None, as_of_hhmm="12:15") == ""


def test_provisional_flow_annotation_renders_actual_fetch_time_not_hardcoded():
    """spec §8: 截至HH:MM is the ACTUAL fetch time threaded from the edge —
    never a hardcoded 12:15 (the 15:45 rerun must render its own time)."""
    from irc.monitor.render_drilldown import provisional_flow_annotation_html
    html = provisional_flow_annotation_html(symbol_value=-1.1, as_of_hhmm="15:47")
    assert "截至15:47" in html
    assert "12:15" not in html


# ── Phase 6: dead-dash column collapse (all_na_columns) ────────────────────────


def test_flow_rollup_html_renders_dark_coverage_chip_when_below_floor():
    from irc.monitor.render_drilldown import flow_rollup_html
    from irc.monitor.holding_metrics import FlowAggregate
    from irc.monitor.types import SignalRecord

    agg = FlowAggregate(value=None, reason="flow_no_coverage", covered_weight_ratio=0.2)
    sig = SignalRecord(fund_id="519069", status="ok", bias="NEUTRAL", composite=0.0,
                       signal_confidence=0.9, available_weight=1.0, present_families=(),
                       contributions=(), divergence_codes=())
    html = flow_rollup_html((), agg, sig)
    assert "暗·覆盖不足" in html


def test_flow_rollup_html_no_chip_when_value_present():
    from irc.monitor.render_drilldown import flow_rollup_html
    from irc.monitor.holding_metrics import FlowAggregate
    from irc.monitor.types import SignalRecord

    agg = FlowAggregate(value=0.3, reason=None, covered_weight_ratio=0.8)
    sig = SignalRecord(fund_id="519069", status="ok", bias="NEUTRAL", composite=0.0,
                       signal_confidence=0.9, available_weight=1.0, present_families=(),
                       contributions=(), divergence_codes=())
    html = flow_rollup_html((), agg, sig)
    assert "暗·覆盖不足" not in html


def test_holdings_board_html_collapses_all_na_industry_column_to_header_note():
    from irc.monitor.render_drilldown import holdings_board_html
    from irc.monitor.holding_metrics import HoldingMetric

    metrics = (
        HoldingMetric(symbol="600000", name="X", weight_pct=10.0, pe=15.0, pb=1.5,
                     pe_percentile=0.4, valuation_state="fair", valuation_reason=None,
                     flow_pct_5d=1.0, flow_pct_20d=1.0, flow_score=0.5, flow_reason=None,
                     industry=None, industry_reason="industry_no_data"),
        HoldingMetric(symbol="600001", name="Y", weight_pct=8.0, pe=12.0, pb=1.2,
                     pe_percentile=0.3, valuation_state="cheap", valuation_reason=None,
                     flow_pct_5d=0.5, flow_pct_20d=0.5, flow_score=0.2, flow_reason=None,
                     industry=None, industry_reason="industry_no_data"),
    )
    html = holdings_board_html(metrics)
    assert "industry_no_data" in html   # structured reason code surfaces in the header note
    assert html.count('<td>') > 0   # rows still render (only the header collapses, not the rows)


def test_holdings_board_html_pb_dark_column_does_not_borrow_flow_reason():
    """F4 (P1, ship-review round 1): an all-dark `pb` column must use the
    valuation leg's own reason, never fall through to an unrelated flow_reason
    just because flow_reason happens to be set on the same rows."""
    from irc.monitor.render_drilldown import holdings_board_html
    from irc.monitor.holding_metrics import HoldingMetric

    metrics = (
        HoldingMetric(symbol="600000", name="X", weight_pct=10.0, pe=None, pb=None,
                     pe_percentile=None, valuation_state=None, valuation_reason=None,
                     flow_pct_5d=1.0, flow_pct_20d=1.0, flow_score=0.5,
                     flow_reason="flow_no_data"),
        HoldingMetric(symbol="600001", name="Y", weight_pct=8.0, pe=None, pb=None,
                     pe_percentile=None, valuation_state=None, valuation_reason=None,
                     flow_pct_5d=0.5, flow_pct_20d=0.5, flow_score=0.2,
                     flow_reason="flow_no_data"),
    )
    html = holdings_board_html(metrics)
    # pb is all-dark but valuation_reason is None on every row -> honest "no
    # semantically-correct reason source" rendering, never borrowed flow_no_data.
    pb_note = html.split("本表全暗列：")[1].split("</p>")[0]
    pb_part = [p for p in pb_note.split("、") if p.startswith("PB")][0]
    assert "flow_no_data" not in pb_part


def test_holdings_board_html_pb_dark_column_uses_valuation_reason_when_present():
    """The honest mapping for pb/pe/pe_percentile/valuation_state IS
    valuation_reason — verify it surfaces when actually set."""
    from irc.monitor.render_drilldown import holdings_board_html
    from irc.monitor.holding_metrics import HoldingMetric

    metrics = (
        HoldingMetric(symbol="600000", name="X", weight_pct=10.0, pe=None, pb=None,
                     pe_percentile=None, valuation_state=None,
                     valuation_reason="no_series",
                     flow_pct_5d=1.0, flow_pct_20d=1.0, flow_score=0.5, flow_reason=None),
    )
    html = holdings_board_html(metrics)
    pb_note = html.split("本表全暗列：")[1].split("</p>")[0]
    pb_part = [p for p in pb_note.split("、") if p.startswith("PB")][0]
    assert "no_series" in pb_part
