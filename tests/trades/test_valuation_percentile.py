from __future__ import annotations
from irc.schemas.valuation import ValuationBucketsConfig
from irc.trades.valuation_percentile import method_for_percentile


def _cfg() -> ValuationBucketsConfig:
    return ValuationBucketsConfig.model_validate({
        "buckets": [
            {"max_percentile": 0.30, "buy_method": "lump_sum",              "granularity": "1-2 tranches"},
            {"max_percentile": 0.60, "buy_method": "dca_weekly",            "granularity": "12-16 weeks"},
            {"max_percentile": 0.80, "buy_method": "dca_weekly_slow",      "granularity": "24-26 weeks"},
            {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold","granularity": "36+ weeks"},
            {"max_percentile": 1.00, "buy_method": "suspend",               "granularity": "n/a"},
        ]
    })


def test_low_percentile_lump_sum():
    out = method_for_percentile(percentile=0.20, cfg=_cfg())
    assert out.buy_method == "lump_sum"


def test_current_us_market_70th_percentile():
    out = method_for_percentile(percentile=0.70, cfg=_cfg())
    assert out.buy_method == "dca_weekly_slow"


def test_extreme_percentile_suspend():
    out = method_for_percentile(percentile=0.97, cfg=_cfg())
    assert out.buy_method == "suspend"
