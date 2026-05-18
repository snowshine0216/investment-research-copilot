from __future__ import annotations
from irc.schemas.triggers import TriggersConfig
from irc.trades.triggers import emit_triggers_for_trade


def _cfg() -> TriggersConfig:
    # Mirrors config/triggers.yaml — the production key is
    # ``weekly_drawdown_4pct``, NOT ``weekly_drawdown``. Tests that hard-code
    # the wrong key let a real bug ship in 2026-05-18: every CN trade row
    # rendered with ``triggers: []`` even though the config defined the rule.
    return TriggersConfig.model_validate({
        "triggers": {
            "vix_high":             {"data_field": "macro.vix",         "comparator": ">",  "threshold": 25.0},
            "real_yield_low":       {"data_field": "macro.real_yield_10y_tips", "comparator": "<=", "threshold": 0.0},
            "weekly_drawdown_4pct": {"data_field": "instrument.weekly_return", "comparator": "<=", "threshold": -0.04},
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
    assert "weekly_drawdown_4pct" in names


def test_cn_etf_anchor_emits_weekly_drawdown_trigger():
    out = emit_triggers_for_trade(asset_class="cn_etf", buy_method="small_account_anchor", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "weekly_drawdown_4pct" in names, f"expected weekly_drawdown_4pct in {names}"


def test_cn_bond_fund_anchor_emits_weekly_drawdown_trigger():
    out = emit_triggers_for_trade(asset_class="cn_bond_fund", buy_method="small_account_anchor", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "weekly_drawdown_4pct" in names


def test_us_etf_anchor_emits_both_vix_and_drawdown():
    # ``_wants_weekly_drawdown`` is intentionally broad: anchor-style methods
    # earn drawdown discipline regardless of asset class. us_etf still keeps
    # its vix trigger alongside the new drawdown one.
    out = emit_triggers_for_trade(asset_class="us_etf", buy_method="small_account_anchor", cfg=_cfg())
    names = [t["name"] for t in out]
    assert "vix_high" in names
    assert "weekly_drawdown_4pct" in names


def test_us_etf_passive_hold_emits_only_vix():
    # A non-anchor, non-dca method on us_etf falls out of the drawdown
    # predicate — proves the predicate isn't matching every us_etf row.
    out = emit_triggers_for_trade(asset_class="us_etf", buy_method="passive_hold", cfg=_cfg())
    names = [t["name"] for t in out]
    assert names == ["vix_high"]
