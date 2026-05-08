from __future__ import annotations
from irc.schemas.triggers import TriggersConfig
from irc.trades.triggers import emit_triggers_for_trade


def _cfg() -> TriggersConfig:
    return TriggersConfig.model_validate({
        "triggers": {
            "vix_high":         {"data_field": "macro.vix",         "comparator": ">",  "threshold": 25.0},
            "real_yield_low":   {"data_field": "macro.real_yield_10y_tips", "comparator": "<=", "threshold": 0.0},
            "weekly_drawdown":  {"data_field": "instrument.weekly_return", "comparator": "<=", "threshold": -0.04},
        }
    })


def test_us_etf_emits_vix_trigger():
    out = emit_triggers_for_trade(asset_class="us_etf", buy_method="dca_weekly_slow", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "vix_high" in names


def test_gold_emits_real_yield():
    out = emit_triggers_for_trade(asset_class="gold", buy_method="gold_anchor_plus_band", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "real_yield_low" in names


def test_dca_buy_method_emits_weekly_drawdown_trigger():
    out = emit_triggers_for_trade(asset_class="cn_equity_fund", buy_method="dca_monthly", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "weekly_drawdown" in names
