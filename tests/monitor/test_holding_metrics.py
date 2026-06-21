# tests/monitor/test_holding_metrics.py
from __future__ import annotations

from dataclasses import dataclass as _dc
from datetime import date, timedelta

import pytest

import pytest as _pt

from irc.monitor.holding_metrics import (
    HoldingMetric,
    _COVERAGE_FLOOR,
    _blend_flow_pct,
    _window_mean,
    aggregate_flow,
    flow_band,
    per_stock_metrics,
    per_stock_valuation,
)
from irc.opportunity.lookthrough_valuation import MetricSeries


# ---------------------------------------------------------------------------
# Task 1.5: flow_band + _blend_flow_pct
# ---------------------------------------------------------------------------

# D7 bands in PERCENT-POINTS: >=3.0→+1.0, 1.0..3.0→+0.5, -1.0..1.0→0.0,
# -3.0..-1.0→-0.5, <=-3.0→-1.0.
@pytest.mark.parametrize("pct,score", [
    (5.0, 1.0), (3.0, 1.0),
    (2.0, 0.5), (1.0, 0.5),
    (0.5, 0.0), (0.0, 0.0), (-0.5, 0.0),
    (-1.0, -0.5), (-2.0, -0.5),
    (-3.0, -1.0), (-5.0, -1.0),
])
def test_flow_band_percent_point_thresholds(pct, score):
    assert flow_band(pct) == score


@pytest.mark.parametrize("ratio_value", [0.01, 0.03])
def test_ratio_unit_canary_lands_in_deadband(ratio_value):
    # 100x inversion guard: a ratio-unit value (0.01 == 1% in ratio) is read as
    # 0.01 PERCENT-POINTS → deadband → 0.0. If someone /100's the flow leg, a real
    # 3.0pp inflow would collapse to 0.03 here and silently score 0.0.
    assert flow_band(ratio_value) == 0.0


def test_blend_favors_20d_with_named_weights():
    # blended = 0.4*5d + 0.6*20d
    assert _blend_flow_pct(5.0, 0.0) == pytest.approx(2.0)
    assert _blend_flow_pct(0.0, 5.0) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Task 1.6: _window_mean
# ---------------------------------------------------------------------------

def test_window_mean_uses_last_n_rows():
    series = tuple((f"2026-06-{d:02d}", float(d)) for d in range(1, 11))  # 1.0..10.0
    assert _window_mean(series, 5) == pytest.approx((6 + 7 + 8 + 9 + 10) / 5)


def test_window_mean_short_series_uses_what_it_has():
    series = (("2026-06-01", 2.0), ("2026-06-02", 4.0))  # <5 rows
    assert _window_mean(series, 5) == pytest.approx(3.0)


def test_window_mean_empty_series_is_none():
    assert _window_mean((), 5) is None


# ---------------------------------------------------------------------------
# Task 1.7: per_stock_valuation
# ---------------------------------------------------------------------------

def _mature_series(code: str, pes: list[float | None], pbs: list[float | None]):
    # 200 daily points to clear the 120-point / 180-day maturity gate.
    base = date(2025, 1, 1)
    pts = tuple(
        ((base + timedelta(days=i)).isoformat(), pes[i], pbs[i]) for i in range(len(pes))
    )
    return MetricSeries(code=code, source="eastmoney", points=pts)


def test_per_stock_valuation_latest_pe_pb_and_percentile():
    n = 200
    pes = [10.0 + i * 0.01 for i in range(n)]   # strictly rising → latest is the max
    pbs = [1.0 + i * 0.001 for i in range(n)]
    series = _mature_series("600519", pes, pbs)
    metric = per_stock_valuation("600519", series)
    assert metric.pe == pytest.approx(pes[-1])
    assert metric.pb == pytest.approx(pbs[-1])
    assert metric.pe_percentile == pytest.approx(1.0)  # latest == historical max
    assert metric.valuation_state == "very_expensive"  # pct 1.0 → expensive band
    assert metric.valuation_reason is None


def test_per_stock_valuation_negative_pe_shows_raw_state_none():
    n = 200
    pes = [-5.0] * n   # no strictly-positive PE point
    pbs = [2.0] * n
    series = _mature_series("000001", pes, pbs)
    metric = per_stock_valuation("000001", series)
    assert metric.pe == pytest.approx(-5.0)          # raw negative shown
    assert metric.pe_percentile is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "pe_not_positive"


def test_per_stock_valuation_immature_history_is_none():
    pes = [10.0 + i * 0.01 for i in range(50)]  # <120 points → immature
    pbs = [1.0] * 50
    series = _mature_series("300750", pes, pbs)
    metric = per_stock_valuation("300750", series)
    assert metric.pe_percentile is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "pe_immature"


def test_per_stock_valuation_no_series_is_none():
    metric = per_stock_valuation("600519", None)
    assert metric.pe is None and metric.pb is None
    assert metric.valuation_state is None
    assert metric.valuation_reason == "no_series"


# ---------------------------------------------------------------------------
# Task 1.8: per_stock_metrics + HoldingMetric
# ---------------------------------------------------------------------------

@_dc(frozen=True)
class _Holding:  # stand-in for ConstituentAnalysis (symbol, name_cn, weight_pct)
    symbol: str
    name_cn: str
    weight_pct: float


def _flow(n_days: int, pct: float):
    base = date(2026, 1, 1)
    return tuple(((base + timedelta(days=i)).isoformat(), pct) for i in range(n_days))


def test_per_stock_metrics_builds_rows_with_flow_windows_and_score():
    holdings = (_Holding("600519", "贵州茅台", 12.0),)
    flow_by_code = {"600519": _flow(20, 4.0)}  # steady +4.0pp → score +1.0
    metrics = per_stock_metrics(holdings, series_by_code={}, flow_series_by_code=flow_by_code)
    m = metrics[0]
    assert isinstance(m, HoldingMetric)
    assert m.symbol == "600519" and m.name == "贵州茅台" and m.weight_pct == 12.0
    assert m.flow_pct_5d == pytest.approx(4.0)
    assert m.flow_pct_20d == pytest.approx(4.0)
    assert m.flow_score == 1.0
    assert m.flow_reason is None


def test_per_stock_metrics_no_flow_series_marks_flow_no_data():
    holdings = (_Holding("600519", "贵州茅台", 12.0),)
    metrics = per_stock_metrics(holdings, series_by_code={}, flow_series_by_code={"600519": None})
    m = metrics[0]
    assert m.flow_score is None
    assert m.flow_reason == "flow_no_data"
    assert m.flow_pct_5d is None and m.flow_pct_20d is None


# ---------------------------------------------------------------------------
# Task 1.9: aggregate_flow + FlowAggregate
# ---------------------------------------------------------------------------

def _metric(symbol, weight, score, reason=None):
    return HoldingMetric(symbol, symbol, weight, None, None, None, None, None,
                         None, None, score, reason)


def test_aggregate_flow_weighted_renorm_over_covered():
    metrics = (
        _metric("a", 30.0, 1.0),
        _metric("b", 10.0, -0.5),
    )
    agg = aggregate_flow(metrics)
    # (30*1.0 + 10*-0.5) / (30+10) = 25/40 = 0.625
    assert agg.value == pytest.approx(0.625)
    assert agg.reason is None
    assert agg.covered_weight_ratio == pytest.approx(1.0)


def test_aggregate_flow_zero_covered_is_flow_no_data():
    metrics = (_metric("a", 30.0, None, "flow_no_data"),)
    agg = aggregate_flow(metrics)
    assert agg.value is None and agg.reason == "flow_no_data"
    assert agg.covered_weight_ratio == pytest.approx(0.0)


def test_aggregate_flow_below_coverage_floor_is_flow_no_coverage():
    # covered weight 10 of total 40 → ratio 0.25 < 0.50 floor.
    metrics = (
        _metric("a", 10.0, 1.0),
        _metric("b", 30.0, None, "flow_no_data"),
    )
    agg = aggregate_flow(metrics)
    assert agg.value is None and agg.reason == "flow_no_coverage"
    assert agg.covered_weight_ratio == pytest.approx(0.25)


def test_aggregate_flow_exactly_at_floor_is_covered():
    # covered weight 20 of total 40 → ratio 0.50 == floor → covered.
    metrics = (
        _metric("a", 20.0, 1.0),
        _metric("b", 20.0, None, "flow_no_data"),
    )
    agg = aggregate_flow(metrics)
    assert agg.value == pytest.approx(1.0)
    assert agg.reason is None
    assert _COVERAGE_FLOOR == 0.50


# ---------------------------------------------------------------------------
# Task 2.2: industry_band + named constants
# ---------------------------------------------------------------------------

from irc.monitor.holding_metrics import (
    industry_band, _FALSE_CHEAP_RICHNESS, _SELF_W, _INDUSTRY_W,
    _MONITOR_COVERAGE_FLOOR,
)


@_pt.mark.parametrize("r,score", [
    (0.50, 1.0), (0.70, 1.0),         # r<=0.70 → +1.0
    (0.80, 0.5), (0.90, 0.5),         # 0.70<r<=0.90 → +0.5
    (1.00, 0.0), (1.10, 0.0),         # 0.90<r<=1.10 → 0.0
    (1.15, -0.5), (1.19, -0.5),       # 1.10<r<1.20 → -0.5
    (1.20, -1.0), (2.00, -1.0),       # r>=1.20 → -1.0 (pinned to _FALSE_CHEAP_RICHNESS)
])
def test_industry_band_asymmetric_raw_r(r, score):
    assert industry_band(r) == score


def test_named_constants_locked():
    assert _SELF_W == 0.60 and _INDUSTRY_W == 0.40
    assert _FALSE_CHEAP_RICHNESS == 1.2
    assert _MONITOR_COVERAGE_FLOOR == 0.40
