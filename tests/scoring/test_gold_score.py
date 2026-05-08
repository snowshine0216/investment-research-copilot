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
