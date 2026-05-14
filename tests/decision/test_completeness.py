from __future__ import annotations

import pytest

from irc.decision.completeness import (
    REQUIRED_METRIC_FIELDS,
    completeness_ratio,
    missing_required_fields,
    summarize_completeness,
)


def test_missing_required_fields_returns_all_fields_for_absent_row() -> None:
    assert missing_required_fields(None) == REQUIRED_METRIC_FIELDS


def test_missing_required_fields_treats_none_and_nan_as_missing() -> None:
    row = {
        "expense_ratio": 0.001,
        "drawdown_3y": None,
        "vol_1y": float("nan"),
        "downside_capture": 0.9,
        "aum_stability_pct": 0.05,
        "manager_tenure_years": 8.0,
        "holdings_concentration_top10": 0.25,
    }

    assert missing_required_fields(row) == ("drawdown_3y", "vol_1y")


def test_completeness_ratio_counts_present_required_fields() -> None:
    row = {
        "expense_ratio": 0.001,
        "drawdown_3y": 0.2,
        "vol_1y": 0.18,
        "downside_capture": 0.9,
        "aum_stability_pct": 0.05,
        "manager_tenure_years": 8.0,
        "holdings_concentration_top10": 0.25,
    }

    assert completeness_ratio(row) == 1.0


def test_summarize_completeness_groups_by_asset_class() -> None:
    rows = [
        {"instrument_id": "A", "asset_class": "gold", "data_completeness": 1.0},
        {"instrument_id": "B", "asset_class": "gold", "data_completeness": 0.0},
        {"instrument_id": "C", "asset_class": "us_etf", "data_completeness": 0.5},
    ]

    summary = summarize_completeness(rows)

    assert summary["overall_avg"] == 0.5
    assert summary["by_asset_class"] == {"gold": 0.5, "us_etf": 0.5}


def test_completeness_ratio_partial_row_returns_fraction() -> None:
    row = {
        "expense_ratio": 0.001,
        "drawdown_3y": None,
        "vol_1y": None,
        "downside_capture": 0.9,
        "aum_stability_pct": float("nan"),
        "manager_tenure_years": 8.0,
        "holdings_concentration_top10": 0.25,
    }

    ratio = completeness_ratio(row)

    assert ratio == pytest.approx(4 / 7)


def test_completeness_ratio_none_row_returns_zero() -> None:
    assert completeness_ratio(None) == 0.0


def test_completeness_ratio_empty_required_returns_one() -> None:
    assert completeness_ratio({"expense_ratio": 0.5}, required=[]) == 1.0


def test_summarize_completeness_empty_list_returns_full_avg() -> None:
    summary = summarize_completeness([])

    assert summary["overall_avg"] == 1.0
    assert summary["by_asset_class"] == {}
