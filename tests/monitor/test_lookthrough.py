from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis
from irc.opportunity.lookthrough_valuation import MetricSeries
from irc.monitor.lookthrough import lookthrough_valuation_state


def _constituent(symbol: str, weight_pct: float) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn="x", weight_pct=weight_pct,
        evidence=(), failure_reasons=(), one_line_view="",
    )


def _snapshot(*constituents: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="519069", source_report_date="2026-03-31",
        source_report_quarter="2026Q1", cache_probed_at="",
        constituent_analyses=tuple(constituents),
        failure_reasons_by_symbol={},
    )


def _rising_series(code: str, n: int = 200) -> MetricSeries:
    # n PE points every 2 days → >120 pts spanning >180d (clears the maturity gate);
    # latest PE is the max → self-history percentile 1.0.
    from datetime import date
    base = date(2025, 1, 1).toordinal()
    points = tuple(
        (date.fromordinal(base + 2 * i).isoformat(), 18.0 + i * 0.01, 2.0)
        for i in range(n)
    )
    return MetricSeries(code=code, source="eastmoney", points=points)


def test_helper_sufficient_coverage_returns_state():
    snap = _snapshot(_constituent("600519", 60.0))
    series = {"600519": _rising_series("600519")}
    assert lookthrough_valuation_state(snap, series) == "very_expensive"


def test_helper_below_floor_is_none():
    # 30% covered < 0.50 floor → None percentile → None state.
    snap = _snapshot(_constituent("600519", 30.0))
    series = {"600519": _rising_series("600519")}
    assert lookthrough_valuation_state(snap, series) is None


def test_helper_no_priced_holdings_is_none():
    # Holdings present, but no matching series → coverage 0.0 → None.
    snap = _snapshot(_constituent("600519", 60.0))
    assert lookthrough_valuation_state(snap, {}) is None


def test_helper_empty_holdings_is_none():
    assert lookthrough_valuation_state(_snapshot(), {}) is None


def test_helper_non_ashare_symbol_does_not_match():
    # HK-style symbol won't be in the A-share-keyed series map → uncovered → None.
    snap = _snapshot(_constituent("00700", 60.0))   # 5-digit HK code
    series = {"600519": _rising_series("600519")}    # unrelated A-share series
    assert lookthrough_valuation_state(snap, series) is None
