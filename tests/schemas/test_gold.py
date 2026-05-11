from __future__ import annotations
import pytest
from pydantic import ValidationError
from irc.schemas.gold import GoldDriversConfig, DriverSpec


def test_gold_drivers_minimal():
    raw = {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {
            "vol_window_months": 6, "vol_baseline_window_months": 12,
            "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25,
        },
        "band": {"rolling_window_months": 6},
    }
    cfg = GoldDriversConfig.model_validate(raw)
    assert sum(d.weight for d in cfg.drivers.values()) == pytest.approx(1.0)


def test_gold_weights_sum_to_one_required():
    raw = {
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.50, "direction": "inverse"},
            "dxy": {"weight": 0.50, "direction": "inverse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12, "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    }
    with pytest.raises(ValidationError):
        GoldDriversConfig.model_validate(raw)


def test_direction_inverse_accepted():
    DriverSpec(weight=0.2, direction="inverse")


def test_direction_invalid_rejected():
    with pytest.raises(ValidationError):
        DriverSpec(weight=0.2, direction="sideways")
