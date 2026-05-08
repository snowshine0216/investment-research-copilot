from __future__ import annotations
from irc.trades.buy_method import default_buy_method, MODE_BUILD


def test_gold_default_anchor_plus_band():
    assert default_buy_method(asset_class="gold", mode="steady_state") == "gold_anchor_plus_band"


def test_us_etf_broad_default_lump_sum():
    assert default_buy_method(asset_class="us_etf", mode="steady_state") == "lump_sum"


def test_cn_active_default_dca_monthly():
    assert default_buy_method(asset_class="cn_equity_fund", mode="steady_state") == "dca_monthly"


def test_build_mode_overrides_with_small_account_anchor():
    # Build mode rotates fills; non-rotation classes default to small_account_anchor
    out = default_buy_method(asset_class="cn_equity_fund", mode=MODE_BUILD)
    assert out == "small_account_anchor"
    # Gold remains anchor regardless
    assert default_buy_method(asset_class="gold", mode=MODE_BUILD) == "gold_anchor_plus_band"
