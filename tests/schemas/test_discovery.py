from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.discovery import DiscoveryConfig, QualityFilters


def test_discovery_config_default():
    raw = {
        "hard_filters": {
            "inception_years_min": 3,
            "cn_fund_aum_cny_min": 500_000_000,
            "us_etf_aum_usd_min": 100_000_000,
            "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 10_000_000,
        },
        "quality_filters": {
            "drawdown_3y_buffer": 1.2,
            "tracking_error_max": 0.015,
            "manager_tenure_years_min": 2,
        },
        "role_bucket": {"min_candidates_per_role": 8, "fail_below": 5},
    }
    cfg = DiscoveryConfig.model_validate(raw)
    assert cfg.hard_filters.inception_years_min == 3


def test_fail_below_gte_min_candidates_fails():
    raw = {
        "hard_filters": {
            "inception_years_min": 3,
            "cn_fund_aum_cny_min": 500_000_000,
            "us_etf_aum_usd_min": 100_000_000,
            "cn_active_expense_ratio_max": 0.015,
            "cn_passive_expense_ratio_max": 0.005,
            "us_etf_expense_ratio_max": 0.003,
            "etf_daily_volume_cny_min": 10_000_000,
        },
        "quality_filters": {
            "drawdown_3y_buffer": 1.2,
            "tracking_error_max": 0.015,
            "manager_tenure_years_min": 2,
        },
        "role_bucket": {"min_candidates_per_role": 5, "fail_below": 8},  # fail_below >= min
    }
    with pytest.raises(ValidationError):
        DiscoveryConfig.model_validate(raw)


def test_hard_filters_qdii_max_premium_pct_default_is_qdii_max_premium_default():
    """AC9: default field value is the named Final constant 0.05."""
    from irc.schemas.discovery import HardFilters, QDII_MAX_PREMIUM_DEFAULT
    assert QDII_MAX_PREMIUM_DEFAULT == 0.05
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
    }
    cfg = HardFilters.model_validate(raw)
    assert cfg.qdii_max_premium_pct == QDII_MAX_PREMIUM_DEFAULT


def test_hard_filters_qdii_max_premium_pct_rejects_negative():
    from irc.schemas.discovery import HardFilters
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
        "qdii_max_premium_pct": -0.01,
    }
    with pytest.raises(ValidationError):
        HardFilters.model_validate(raw)


def test_hard_filters_qdii_max_premium_pct_accepts_yaml_override():
    from irc.schemas.discovery import HardFilters
    raw = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
        "qdii_max_premium_pct": 0.08,
    }
    cfg = HardFilters.model_validate(raw)
    assert cfg.qdii_max_premium_pct == 0.08


def test_qdii_max_premium_pct_rejects_zero():
    """P1-2 fix: gt=0 — zero or negative threshold is invalid configuration."""
    from irc.schemas.discovery import HardFilters
    _base = {
        "inception_years_min": 3,
        "cn_fund_aum_cny_min": 500_000_000,
        "us_etf_aum_usd_min": 100_000_000,
        "cn_active_expense_ratio_max": 0.015,
        "cn_passive_expense_ratio_max": 0.005,
        "us_etf_expense_ratio_max": 0.003,
        "etf_daily_volume_cny_min": 10_000_000,
    }
    with pytest.raises(ValidationError):
        HardFilters.model_validate({**_base, "qdii_max_premium_pct": 0.0})
    with pytest.raises(ValidationError):
        HardFilters.model_validate({**_base, "qdii_max_premium_pct": -0.01})


def test_small_drawdown_buffer_accepted():
    QualityFilters(drawdown_3y_buffer=0.1, tracking_error_max=0.02, manager_tenure_years_min=0)


def test_extreme_tracking_error_max_accepted():
    QualityFilters(drawdown_3y_buffer=1.0, tracking_error_max=1.0, manager_tenure_years_min=2)
