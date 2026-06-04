from __future__ import annotations

from irc.opportunity.lookthrough_diff_report import (
    FundDiffRow,
    build_floor_sensitivity,
    build_fund_diff_row,
    render_diff_report,
)
from irc.opportunity.lookthrough_valuation import FundValuationResult, MetricCoverage


def _result(pe_pct, pb_pct):
    return FundValuationResult(
        pe=MetricCoverage(pe_pct, 0.60, ("600519",), ("eastmoney",)),
        pb=MetricCoverage(pb_pct, 0.55, ("600519",), ("eastmoney", "tushare")),
    )


def test_build_fund_diff_row_flags_band_flip_and_delta() -> None:
    # NAV percentile 0.15 (cheap band) vs PE percentile 0.50 (fair band) → flip.
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.15, result=_result(0.50, 0.45),
    )
    assert isinstance(row, FundDiffRow)
    assert row.would_flip is True
    assert abs(row.delta_percentile - 0.35) < 1e-9
    assert row.pe_coverage_ratio == 0.60
    assert row.pb_source_mix == ("eastmoney", "tushare")


def test_build_fund_diff_row_no_flip_same_band() -> None:
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.50, result=_result(0.55, None),
    )
    assert row.would_flip is False


def test_build_fund_diff_row_handles_none_pe_percentile() -> None:
    # PE None (below floor / immature) → no flip, delta None, band reported as "—".
    row = build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.20, result=_result(None, None),
    )
    assert row.would_flip is False
    assert row.delta_percentile is None


def test_floor_sensitivity_counts_grounded_funds_per_floor() -> None:
    # Three funds with coverage ratios 0.42 / 0.55 / 0.65.
    coverage_ratios = [0.42, 0.55, 0.65]
    table = build_floor_sensitivity(coverage_ratios, floors=(0.40, 0.50, 0.60))
    assert table[0.40] == 3  # all meet 0.40
    assert table[0.50] == 2  # 0.55, 0.65
    assert table[0.60] == 1  # 0.65 only


def test_render_diff_report_includes_caveat_and_table() -> None:
    rows = [build_fund_diff_row(
        instrument_id="AF1", name_cn="主动基金",
        nav_percentile=0.15, result=_result(0.50, 0.45),
    )]
    text = render_diff_report(rows, build_floor_sensitivity([0.60], floors=(0.40, 0.50, 0.60)))
    assert "current-basket" in text.lower() or "当前持仓" in text
    assert "0.40" in text and "0.50" in text and "0.60" in text
    assert "AF1" in text
