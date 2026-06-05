from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.valuation import ActiveFundLookthroughConfig, ValuationBucketsConfig


def test_active_fund_lookthrough_defaults_disabled() -> None:
    cfg = ActiveFundLookthroughConfig()
    assert cfg.enabled is False
    assert cfg.coverage_floor == 0.50
    assert cfg.pb_uses_pe_gate is False


def test_valuation_buckets_config_has_default_lookthrough_block() -> None:
    cfg = ValuationBucketsConfig(
        buckets=[{"max_percentile": 1.0, "buy_method": "suspend", "granularity": "n/a"}]
    )
    # Default-disabled when YAML omits the block (back-compat for existing tests).
    assert cfg.active_fund_lookthrough.enabled is False


def test_coverage_floor_must_be_a_ratio() -> None:
    with pytest.raises(ValueError):
        ActiveFundLookthroughConfig(coverage_floor=1.5)
    with pytest.raises(ValueError):
        ActiveFundLookthroughConfig(coverage_floor=0.0)


def test_buckets_must_be_ordered():
    raw = {
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum", "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly", "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow", "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold", "granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend", "granularity": "n/a"},
        ]
    }
    cfg = ValuationBucketsConfig.model_validate(raw)
    assert cfg.buckets[0].max_percentile == 0.30


def test_buckets_disordered_fails():
    raw = {
        "buckets": [
            {"max_percentile": 0.60, "buy_method": "lump_sum", "granularity": "x"},
            {"max_percentile": 0.30, "buy_method": "dca_weekly", "granularity": "x"},
        ]
    }
    with pytest.raises(ValidationError, match="ascending"):
        ValuationBucketsConfig.model_validate(raw)


def test_buckets_last_must_be_1_0():
    """Last bucket must cover the 100th percentile; ending at 0.95 is rejected."""
    raw = {
        "buckets": [
            {"max_percentile": 0.50, "buy_method": "lump_sum", "granularity": "x"},
            {"max_percentile": 0.95, "buy_method": "suspend", "granularity": "n/a"},
        ]
    }
    with pytest.raises(ValidationError, match="1.0"):
        ValuationBucketsConfig.model_validate(raw)
