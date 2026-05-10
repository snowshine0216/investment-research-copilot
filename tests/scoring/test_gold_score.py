from __future__ import annotations
from irc.schemas.gold import GoldDriversConfig
from irc.scoring.gold_score import compute_gold_score, GoldDriverInputs, gold_tilt_from_score


def _cfg() -> GoldDriversConfig:
    return GoldDriversConfig.model_validate({
        "drivers": {
            "real_yield_10y_tips": {"weight": 0.25, "direction": "inverse"},
            "dxy": {"weight": 0.15, "direction": "inverse"},
            "inflation_5y5y": {"weight": 0.15, "direction": "positive"},
            "cb_purchases_wgc": {"weight": 0.15, "direction": "positive_slow"},
            "etf_holdings_gld": {"weight": 0.15, "direction": "confirmation_short"},
            "geopolitical_proxy": {"weight": 0.15, "direction": "positive_pulse"},
        },
        "regime_detection": {"vol_window_months": 6, "vol_baseline_window_months": 12,
                              "vol_ratio_range_threshold": 1.5, "adx_range_threshold": 25},
        "band": {"rolling_window_months": 6},
    })


def _inputs_bullish() -> GoldDriverInputs:
    return GoldDriverInputs(
        real_yield_10y_tips=0.20, dxy=98.0, inflation_5y5y=2.50,
        cb_purchases_yearly_tons=1100, etf_holdings_30d_change_tons=15,
        geopolitical_stress_0to1=0.8,
    )


def test_bullish_inputs_score_high():
    s = compute_gold_score(_inputs_bullish(), _cfg())
    assert s >= 70


def test_bearish_inputs_score_low():
    inp = GoldDriverInputs(
        real_yield_10y_tips=2.8, dxy=112.0, inflation_5y5y=1.80,
        cb_purchases_yearly_tons=200, etf_holdings_30d_change_tons=-30,
        geopolitical_stress_0to1=0.1,
    )
    s = compute_gold_score(inp, _cfg())
    assert s <= 35


def test_tilt_mapping():
    assert gold_tilt_from_score(85) == "overweight"
    assert gold_tilt_from_score(65) == "neutral_plus"
    assert gold_tilt_from_score(50) == "neutral"
    assert gold_tilt_from_score(35) == "neutral_minus"
    assert gold_tilt_from_score(15) == "underweight"


def test_known_drivers_present_in_gold_drivers_config():
    """Regression: _KNOWN_DRIVERS keys must match gold_drivers.yaml to avoid KeyError at runtime."""
    from pathlib import Path
    import yaml
    from irc.scoring.gold_score import _KNOWN_DRIVERS
    config_path = Path(__file__).parents[2] / "config" / "gold_drivers.yaml"
    if not config_path.exists():
        import pytest
        pytest.skip("config/gold_drivers.yaml not present in this checkout")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    driver_keys = set((data.get("drivers") or {}).keys())
    missing = set(_KNOWN_DRIVERS) - driver_keys
    assert not missing, f"_KNOWN_DRIVERS references keys not in gold_drivers.yaml: {missing}"


import pytest
from irc.scoring.gold_score import compute_gold_score, GoldDriverInputs, ConfigKeyMismatch
from irc.schemas.gold import GoldDriversConfig


def test_unknown_driver_raises_clear_error():
    """Test that a config missing expected drivers raises ConfigKeyMismatch."""
    bad_cfg = GoldDriversConfig.model_construct(drivers={})
    inputs = GoldDriverInputs(
        real_yield_10y_tips=1.0, dxy=100.0, inflation_5y5y=2.0,
        cb_purchases_yearly_tons=500, etf_holdings_30d_change_tons=0,
        geopolitical_stress_0to1=0.5,
    )
    with pytest.raises(ConfigKeyMismatch):
        compute_gold_score(inputs, bad_cfg)
