from __future__ import annotations

import pytest

from irc.decision.completeness import (
    REQUIRED_METRIC_FIELDS,
    completeness_ratio,
    missing_required_fields,
    required_for_asset_class,
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


def test_required_for_asset_class_drops_aum_stability_universally() -> None:
    for cls in ("cn_etf", "cn_equity_fund", "cn_bond_fund", "gold", "us_etf", "hk_etf"):
        assert "aum_stability_pct" not in required_for_asset_class(cls)


def test_required_for_cn_etf_drops_holdings_concentration() -> None:
    req = required_for_asset_class("cn_etf")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" in req  # ETFs DO have equity downside capture
    assert "manager_tenure_years" in req


def test_required_for_cn_bond_fund_drops_both_holdings_and_downside() -> None:
    req = required_for_asset_class("cn_bond_fund")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" not in req


def test_required_for_gold_drops_holdings_and_downside() -> None:
    req = required_for_asset_class("gold")
    assert "holdings_concentration_top10" not in req
    assert "downside_capture" not in req
    assert "manager_tenure_years" not in req


def test_required_for_active_equity_fund_keeps_holdings_concentration() -> None:
    req = required_for_asset_class("cn_equity_fund")
    assert "holdings_concentration_top10" in req  # active funds DO report top-10


def test_required_for_unknown_asset_class_falls_back_to_default() -> None:
    """Unrecognized asset_class should not silently drop everything — it falls
    back to the full set minus aum_stability_pct."""
    req = required_for_asset_class("unknown_class_xyz")
    assert "expense_ratio" in req
    assert "holdings_concentration_top10" in req
    assert "aum_stability_pct" not in req


def test_completeness_ratio_uses_asset_class_when_provided() -> None:
    """A gold instrument missing only holdings_concentration_top10 + downside_capture
    should score 1.0, not 5/7, because those aren't required for gold."""
    row = {
        "expense_ratio": 0.005, "drawdown_3y": 0.18, "vol_1y": 0.25,
        "manager_tenure_years": 7.0,
        # aum_stability_pct, holdings_concentration_top10, downside_capture all missing
    }
    assert completeness_ratio(row, asset_class="gold") == 1.0


def test_completeness_ratio_falls_back_to_full_required_when_no_asset_class() -> None:
    """Back-compat: omitting asset_class uses the full REQUIRED_METRIC_FIELDS."""
    row = {f: 1.0 for f in REQUIRED_METRIC_FIELDS}
    assert completeness_ratio(row) == 1.0


def test_missing_required_fields_uses_asset_class_when_provided() -> None:
    row = {"expense_ratio": 0.005}
    missing = missing_required_fields(row, asset_class="gold")
    # Gold requires expense_ratio, drawdown_3y, vol_1y. Manager tenure, holdings
    # concentration, downside capture, and AUM stability are not meaningful for
    # passively/physically backed gold ETFs and are intentionally not required.
    assert "drawdown_3y" in missing
    assert "vol_1y" in missing
    assert "manager_tenure_years" not in missing
    assert "holdings_concentration_top10" not in missing
    assert "downside_capture" not in missing
    assert "aum_stability_pct" not in missing
