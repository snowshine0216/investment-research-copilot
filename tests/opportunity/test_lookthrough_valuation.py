from __future__ import annotations

import dataclasses

import pytest

from irc.opportunity.lookthrough_valuation import (
    HoldingWeight,
    MetricCoverage,
    MetricSeries,
    _covered_codes_for_metric,
    fund_valuation_percentile,
)


def _series(code, source, points):
    return MetricSeries(code=code, source=source, points=tuple(points))


def test_metric_coverage_is_frozen() -> None:
    mc = MetricCoverage(percentile=0.5, coverage_ratio=0.6, covered_codes=("600519",),
                        source_mix=("eastmoney",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        mc.percentile = 0.9  # type: ignore[misc]


def test_covered_codes_excludes_non_positive_and_missing_pe() -> None:
    # 600519 has positive PE; 000001 has a non-positive PE; 600000 has no series.
    holdings = (
        HoldingWeight("600519", 30.0),
        HoldingWeight("000001", 25.0),
        HoldingWeight("600000", 20.0),
    )
    series = {
        "600519": _series("600519", "eastmoney", [("2026-05-30", 18.0, 2.0)]),
        "000001": _series("000001", "eastmoney", [("2026-05-30", -5.0, 1.5)]),
    }
    covered = _covered_codes_for_metric(holdings, series, metric="pe")
    assert covered == ("600519",)


def test_covered_codes_pb_independent_of_pe() -> None:
    # 000001 has a non-positive PE (excluded from PE) but a positive PB (kept for PB).
    holdings = (HoldingWeight("000001", 25.0),)
    series = {"000001": _series("000001", "eastmoney", [("2026-05-30", -5.0, 1.5)])}
    assert _covered_codes_for_metric(holdings, series, metric="pe") == ()
    assert _covered_codes_for_metric(holdings, series, metric="pb") == ("000001",)


from irc.opportunity.lookthrough_valuation import _coverage_ratio, _meets_floor


def test_coverage_ratio_divides_percent_by_100() -> None:
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    assert abs(_coverage_ratio(holdings, ("600519", "000001")) - 0.55) < 1e-9


def test_coverage_ratio_only_counts_covered_codes() -> None:
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    assert abs(_coverage_ratio(holdings, ("600519",)) - 0.30) < 1e-9


def test_floor_compares_ratio_not_raw_percent_sum_p0() -> None:
    # P0 regression: raw Σ weight_pct ≈ 55, ratio 0.55. Floor 0.50 must PASS on
    # the RATIO. If the code compared the raw percent sum (55) against 0.50,
    # every fund would pass — this asserts that bug cannot recur.
    holdings = (HoldingWeight("600519", 30.0), HoldingWeight("000001", 25.0))
    ratio = _coverage_ratio(holdings, ("600519", "000001"))
    assert ratio == 0.55
    assert _meets_floor(ratio, coverage_floor=0.50) is True
    # And a basket whose ratio is below the floor must FAIL.
    low = _coverage_ratio((HoldingWeight("600519", 30.0),), ("600519",))
    assert low == 0.30
    assert _meets_floor(low, coverage_floor=0.50) is False


from irc.opportunity.lookthrough_valuation import _aggregate_metric_series


def test_worked_harmonic_two_stock_equal_weight() -> None:
    # Two equal-weight holdings, PE 10 and PE 30 on a single date.
    # EY = 0.5*(1/10) + 0.5*(1/30) = 0.05 + 0.016666... = 0.066666...
    # PE_fund = 1 / 0.066666... = 15.0 (harmonic mean, NOT arithmetic 20).
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney", (("2026-05-30", 10.0, None),)),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.50,
    )
    assert list(out.index.astype(str)) == ["2026-05-30"]
    assert abs(float(out.iloc[-1]) - 15.0) < 1e-9


def test_per_date_renormalization_with_shorter_history() -> None:
    # A has 2 dates, B has only the later date. On the earlier date only A is
    # present, so its renormalized weight is 1.0 → PE_fund = A's PE = 10.0.
    # On the later date both present → harmonic of 10 and 30 at equal weight = 15.
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", 10.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.40,
    )
    vals = {str(d): float(v) for d, v in out.items()}
    assert abs(vals["2026-05-01"] - 10.0) < 1e-9   # only A present
    assert abs(vals["2026-05-30"] - 15.0) < 1e-9   # both present


def test_per_date_drops_dates_below_present_weight_floor() -> None:
    # A (weight 10%) alone on the early date → present ratio 0.10 < floor 0.50
    # → that date is dropped. Both present on the later date → kept.
    holdings = (HoldingWeight("A", 10.0), HoldingWeight("B", 45.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", 10.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.50,
    )
    assert list(out.index.astype(str)) == ["2026-05-30"]


def test_non_positive_metric_value_excluded_per_date() -> None:
    # A's value flips negative on the early date → excluded that date; only B's
    # later positive date survives (A positive again contributes there).
    holdings = (HoldingWeight("A", 25.0), HoldingWeight("B", 25.0))
    series = {
        "A": MetricSeries("A", "eastmoney",
                          (("2026-05-01", -5.0, None), ("2026-05-30", 10.0, None))),
        "B": MetricSeries("B", "eastmoney", (("2026-05-30", 30.0, None),)),
    }
    out = _aggregate_metric_series(
        holdings, series, ("A", "B"), metric="pe", coverage_floor=0.40,
    )
    # Early date: only B present? No — B has no early point; A's is negative.
    # So early date has no positive contributor → dropped. Later date → 15.0.
    assert list(out.index.astype(str)) == ["2026-05-30"]
    assert abs(float(out.iloc[-1]) - 15.0) < 1e-9


import pandas as pd

from irc.opportunity.lookthrough_valuation import _percentile_for_metric


def _ramp_series(n: int, span_days: int) -> pd.Series:
    dates = pd.date_range("2025-01-01", periods=n, freq=f"{max(span_days // max(n - 1, 1), 1)}D")
    return pd.Series([float(i + 1) for i in range(n)], index=dates)


def test_pe_percentile_none_when_below_120_points() -> None:
    # 100 points over a 365-day span: clears the day-span bar but NOT 120 points.
    s = pd.Series([float(i + 1) for i in range(100)],
                  index=pd.date_range("2025-01-01", periods=100, freq="4D"))
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pe_percentile_none_when_span_below_180_days() -> None:
    # 130 points but crammed into < 180 days → fails the day-span half of the gate.
    s = pd.Series([float(i + 1) for i in range(130)],
                  index=pd.date_range("2025-01-01", periods=130, freq="1D"))  # 129 days
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pe_percentile_present_when_gate_cleared() -> None:
    # 200 points over ~398 days → clears both halves. Latest is the max → 1.0.
    s = pd.Series([float(i + 1) for i in range(200)],
                  index=pd.date_range("2025-01-01", periods=200, freq="2D"))
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) == 1.0


def test_pb_percentile_ignores_120_180_gate_uses_only_30_floor() -> None:
    # 40 points, ~40-day span: fails the 120/180 gate but clears the <30 floor.
    # PB (pb_uses_pe_gate=False) returns a percentile; PE on the same series → None.
    s = pd.Series([float(i + 1) for i in range(40)],
                  index=pd.date_range("2025-01-01", periods=40, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=False) == 1.0
    assert _percentile_for_metric(s, metric="pe", pb_uses_pe_gate=False) is None


def test_pb_percentile_none_below_30_floor() -> None:
    s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2025-01-01", periods=3, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=False) is None


def test_pb_with_pe_gate_flag_applies_120_180() -> None:
    # When pb_uses_pe_gate=True, PB inherits the 120/180 gate (flippable call).
    s = pd.Series([float(i + 1) for i in range(40)],
                  index=pd.date_range("2025-01-01", periods=40, freq="1D"))
    assert _percentile_for_metric(s, metric="pb", pb_uses_pe_gate=True) is None
