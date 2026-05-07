from __future__ import annotations
from irc.schemas.discovery import DiscoveryConfig


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
