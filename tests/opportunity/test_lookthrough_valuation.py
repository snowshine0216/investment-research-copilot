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
