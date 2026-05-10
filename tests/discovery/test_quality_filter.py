from __future__ import annotations

import pandas as pd

from irc.schemas.discovery import DiscoveryConfig
from irc.schemas.inputs import RiskBand
from irc.discovery.universe import UniverseRow
from irc.discovery.quality_filter import apply_quality_filter


def _row(iid: str) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class="us_etf", currency="cny",
        tracked_index="x", theme=None, venue_required=(),
    )


def _cfg() -> DiscoveryConfig:
    return DiscoveryConfig.model_validate({
        "hard_filters": {
            "inception_years_min": 3, "cn_fund_aum_cny_min": 5e8,
            "us_etf_aum_usd_min": 1e8, "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005, "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 1e7,
        },
        "quality_filters": {"drawdown_3y_buffer": 1.2, "tracking_error_max": 0.015, "manager_tenure_years_min": 2},
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    })


def test_quality_filter_pass_within_user_dd_band() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "X", "drawdown_3y": 0.18,
        "tracking_error": 0.005, "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert len(out.passed) == 1


def test_quality_filter_fail_above_dd_buffer() -> None:
    # buffer 1.2x of upper band 0.20 = 0.24; dd 0.30 > 0.24 → fail
    metrics = pd.DataFrame([{
        "instrument_id": "X", "drawdown_3y": 0.30,
        "tracking_error": 0.005, "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()
    assert "drawdown" in out.rejected[0].reasons[0].lower()


def test_quality_filter_relaxes_passive_tracking_error_only() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "X", "drawdown_3y": 0.10,
        "tracking_error": 0.020, "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()  # tracking_error 0.020 > 0.015


def test_quality_filter_rejects_nan_required_metrics() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "X", "drawdown_3y": float("nan"),
        "tracking_error": float("nan"), "manager_tenure_years": 5,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("X"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    reasons = " ".join(out.rejected[0].reasons)
    assert out.passed == ()
    assert "missing drawdown_3y" in reasons
    assert "missing tracking_error" in reasons


def _active_row(iid: str) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class="cn_equity_fund", currency="cny",
        tracked_index=None, theme=None, venue_required=(),
    )


def _on_exchange_bond_row(iid: str) -> UniverseRow:
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_on_exchange",
        name_cn=iid, asset_class="cn_bond_fund", currency="cny",
        tracked_index="5年国债", theme=None, venue_required=(),
    )


def _fund_row(iid: str) -> UniverseRow:
    """Non-ETF passive fund (no 'etf' in asset_class, not equity/bond active fund)."""
    return UniverseRow(
        instrument_id=iid, ticker=iid, market="cn_off_exchange",
        name_cn=iid, asset_class="cn_etf", currency="cny",
        tracked_index=None, theme=None, venue_required=(),
    )


def test_quality_filter_no_metrics_row_rejects() -> None:
    metrics = pd.DataFrame(columns=["instrument_id", "drawdown_3y", "tracking_error", "manager_tenure_years"])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_row("MISSING"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()
    assert "no metrics" in out.rejected[0].reasons[0]


def test_quality_filter_active_fund_missing_tenure_rejects() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "F", "drawdown_3y": 0.10,
        "tracking_error": None, "manager_tenure_years": None,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_active_row("F"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()
    assert any("missing manager_tenure_years" in r for r in out.rejected[0].reasons)


def test_quality_filter_active_fund_below_tenure_min_rejects() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "F", "drawdown_3y": 0.10,
        "tracking_error": 0.005, "manager_tenure_years": 0.5,  # below 2y min
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_active_row("F"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert out.passed == ()
    assert any("manager_tenure" in r for r in out.rejected[0].reasons)


def test_quality_filter_non_etf_ignores_tracking_error() -> None:
    """cn_equity_fund has no 'etf' in asset_class — tracking_error check is skipped."""
    metrics = pd.DataFrame([{
        "instrument_id": "F", "drawdown_3y": 0.10,
        "tracking_error": None, "manager_tenure_years": 5.0,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})
    out = apply_quality_filter(rows=(_active_row("F"),), metrics=metrics, cfg=_cfg(), risk_band=risk)
    assert len(out.passed) == 1


def test_quality_filter_on_exchange_bond_etf_does_not_require_manager_tenure() -> None:
    metrics = pd.DataFrame([{
        "instrument_id": "BOND", "drawdown_3y": 0.05,
        "tracking_error": None, "manager_tenure_years": None,
    }])
    risk = RiskBand.model_validate({"max_drawdown": [0.10, 0.20], "horizon": "long_core_medium_rotation"})

    out = apply_quality_filter(
        rows=(_on_exchange_bond_row("BOND"),), metrics=metrics, cfg=_cfg(), risk_band=risk
    )

    assert len(out.passed) == 1
