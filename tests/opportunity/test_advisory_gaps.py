"""Pure-logic tests for src/irc/opportunity/advisory_gaps.py."""
from __future__ import annotations

from irc.fundamentals.types import ActiveFundSnapshot, ConstituentAnalysis


def _analysis(symbol: str, weight_pct: float, failures: tuple[str, ...] = ()) -> ConstituentAnalysis:
    return ConstituentAnalysis(
        symbol=symbol, name_cn=symbol, weight_pct=weight_pct,
        evidence=(), failure_reasons=failures, one_line_view="",
    )


def _snap(*analyses: ConstituentAnalysis) -> ActiveFundSnapshot:
    return ActiveFundSnapshot(
        fund_id="000001", source_report_date="", source_report_quarter="2026Q1",
        cache_probed_at="", constituent_analyses=analyses,
        failure_reasons_by_symbol={},
    )


def test_count_broker_empty_top5_counts_only_top5_with_broker_empty():
    from irc.opportunity.advisory_gaps import count_broker_empty_top5
    snap = _snap(
        _analysis("A", 10.0, ("broker_empty:A",)),
        _analysis("B", 9.0, ("broker_empty:B",)),
        _analysis("C", 8.0, ()),
        _analysis("D", 7.0, ()),
        _analysis("E", 6.0, ()),
        _analysis("F", 1.0, ("broker_empty:F",)),  # outside Top-5
    )
    assert count_broker_empty_top5(snap) == 2


def test_weight_broker_empty_top5_sums_only_top5_with_broker_empty():
    from irc.opportunity.advisory_gaps import weight_broker_empty_top5
    snap = _snap(
        _analysis("A", 12.0, ("broker_empty:A",)),
        _analysis("B", 10.0, ("broker_empty:B",)),
        _analysis("C", 8.0, ()),
        _analysis("D", 7.0, ()),
        _analysis("E", 6.0, ()),
    )
    assert weight_broker_empty_top5(snap) == 22.0


def test_should_emit_returns_true_when_count_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 4.0, ("broker_empty:B",)),
        _analysis("C", 3.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_returns_true_when_weight_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    # Single 25%-weight Top-1 with broker_empty triggers the weight disjunct.
    snap = _snap(
        _analysis("A", 25.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_false_when_neither_threshold_met():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 10.0, ("broker_empty:A",)),
        _analysis("B", 5.0, ()),
    )
    assert should_emit_top_holdings_broker_thin(snap) is False


def test_should_emit_false_on_empty_snapshot():
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap()
    assert should_emit_top_holdings_broker_thin(snap) is False


def test_should_emit_count_boundary_inclusive():
    """`>=2` is boundary-inclusive (mirrors FOREIGN_HEAVY_THRESHOLD precedent)."""
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(
        _analysis("A", 5.0, ("broker_empty:A",)),
        _analysis("B", 4.0, ("broker_empty:B",)),
    )
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_should_emit_weight_boundary_inclusive():
    """`>=20.0` is boundary-inclusive."""
    from irc.opportunity.advisory_gaps import should_emit_top_holdings_broker_thin
    snap = _snap(_analysis("A", 20.0, ("broker_empty:A",)))
    assert should_emit_top_holdings_broker_thin(snap) is True


def test_advisory_gap_codes_contains_top_holdings_broker_thin():
    from irc.opportunity.advisory_gaps import ADVISORY_GAP_CODES
    assert "top_holdings_broker_thin" in ADVISORY_GAP_CODES


def test_threshold_constants_are_named():
    """ADR 0005 + spec AC3: magic numbers must have names."""
    from irc.opportunity.advisory_gaps import (
        TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD,
        TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD,
    )
    assert TOP_HOLDINGS_BROKER_THIN_COUNT_THRESHOLD == 2
    assert TOP_HOLDINGS_BROKER_THIN_WEIGHT_PCT_THRESHOLD == 20.0
