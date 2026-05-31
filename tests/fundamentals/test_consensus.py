from __future__ import annotations

import pytest

from irc.fundamentals.consensus import consensus_upside_pct
from irc.fundamentals.types import BrokerReport


def _report(target: float | None) -> BrokerReport:
    return BrokerReport(
        symbol="600519.SH",
        broker="中信证券",
        rating="买入",
        target_price=target,
        published_iso="2026-05-08",
        title="t",
    )


def test_no_reports_returns_none() -> None:
    assert consensus_upside_pct((), 100.0) is None


def test_all_targets_none_returns_none() -> None:
    reports = (_report(None), _report(None))
    assert consensus_upside_pct(reports, 100.0) is None


def test_single_target_positive_close() -> None:
    # median([120]) / 100 - 1 = 0.20 (ratio units)
    reports = (_report(120.0),)
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_odd_target_count_uses_middle() -> None:
    # median([90, 120, 150]) = 120 ; 120/100 - 1 = 0.20
    reports = (_report(90.0), _report(120.0), _report(150.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_even_target_count_uses_two_middle_mean() -> None:
    # median([100, 110, 130, 160]) = (110+130)/2 = 120 ; 120/100 - 1 = 0.20
    reports = (_report(100.0), _report(110.0), _report(130.0), _report(160.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.20)


def test_mixed_none_targets_ignored() -> None:
    # non-None targets [120, 80] -> median 100 ; 100/100 - 1 = 0.0
    reports = (_report(120.0), _report(None), _report(80.0))
    assert consensus_upside_pct(reports, 100.0) == pytest.approx(0.0)


def test_latest_close_none_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), None) is None


def test_latest_close_zero_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), 0.0) is None


def test_latest_close_negative_returns_none() -> None:
    assert consensus_upside_pct((_report(120.0),), -5.0) is None


def test_latest_close_nan_returns_none() -> None:
    # NaN comparisons are always False, so a bare `<= 0` guard would let NaN
    # through and yield median/nan == nan in a float|None field (adversarial A1).
    assert consensus_upside_pct((_report(120.0),), float("nan")) is None


def test_nan_targets_filtered_like_none() -> None:
    # A NaN target_price is not None, so it must be filtered explicitly or it
    # poisons median() -> nan. All-NaN targets behave like all-None: None.
    reports = (_report(float("nan")), _report(float("nan")))
    assert consensus_upside_pct(reports, 100.0) is None
    # Mixed: NaN ignored, real target drives the result.
    mixed = (_report(float("nan")), _report(120.0))
    assert consensus_upside_pct(mixed, 100.0) == pytest.approx(0.20)
