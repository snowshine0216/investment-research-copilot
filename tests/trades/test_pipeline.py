from __future__ import annotations
from irc.schemas.universe import UniverseConfig
from irc.schemas.valuation import ValuationBucketsConfig
from irc.schemas.triggers import TriggersConfig
from irc.trades.pipeline import build_trade_plan, TradePlanRow


def _u() -> UniverseConfig:
    return UniverseConfig.model_validate({"instruments": [
        {"instrument_id": "VTI", "ticker": "VTI", "market": "us_on_exchange",
         "name_cn": "VTI", "asset_class": "us_etf", "currency": "usd",
         "tracked_index": "S&P 500", "venue_required": ["us_brokerage"]},
        {"instrument_id": "006075", "ticker": "006075", "market": "cn_off_exchange",
         "name_cn": "易方达标普500", "asset_class": "us_etf", "currency": "cny",
         "tracked_index": "S&P 500", "venue_required": ["cmb_fund"]},
    ]})


def _vc() -> ValuationBucketsConfig:
    return ValuationBucketsConfig.model_validate({"buckets": [
        {"max_percentile": 0.30, "buy_method": "lump_sum",          "granularity": "1-2"},
        {"max_percentile": 0.60, "buy_method": "dca_weekly",        "granularity": "12-16"},
        {"max_percentile": 0.80, "buy_method": "dca_weekly_slow",  "granularity": "24-26"},
        {"max_percentile": 0.95, "buy_method": "dca_monthly_threshold","granularity":"36+"},
        {"max_percentile": 1.00, "buy_method": "suspend",           "granularity": "n/a"},
    ]})


def _tg() -> TriggersConfig:
    return TriggersConfig.model_validate({"triggers": {
        "vix_high":        {"data_field": "macro.vix",         "comparator": ">",  "threshold": 25.0},
        "real_yield_low":  {"data_field": "macro.real_yield_10y_tips","comparator": "<=", "threshold": 0.0},
        "weekly_drawdown": {"data_field": "instrument.weekly_return", "comparator": "<=", "threshold": -0.04},
    }})


def test_trade_plan_uses_proxy_when_venue_incompatible():
    selected = [{"instrument_id": "VTI", "asset_class": "us_etf", "target_weight": 0.18,
                 "intra_class_share": 1.0, "composite_score": 75, "role": "core_us_equity"}]
    rows = build_trade_plan(
        selected_instruments=selected, mode="hybrid",
        valuation_percentiles={"us_etf": 0.65},
        available_venues=["cmb_fund"],
        universe=_u(), valuation=_vc(), triggers=_tg(),
    )
    assert any(r["target"] == "006075" for r in rows)


def test_trade_plan_includes_buy_method_and_triggers():
    selected = [{"instrument_id": "510300", "asset_class": "cn_etf", "target_weight": 0.10,
                 "intra_class_share": 1.0, "composite_score": 70, "role": "core_cn_equity"}]
    universe = UniverseConfig.model_validate({"instruments": [
        {"instrument_id": "510300", "ticker": "510300", "market": "cn_on_exchange",
         "name_cn": "沪深300ETF", "asset_class": "cn_etf", "currency": "cny",
         "tracked_index": "沪深300", "venue_required": ["cn_brokerage"]},
    ]})
    rows = build_trade_plan(
        selected_instruments=selected, mode="hybrid",
        valuation_percentiles={"cn_etf": 0.20},
        available_venues=["cn_brokerage"], universe=universe,
        valuation=_vc(), triggers=_tg(),
    )
    assert rows[0]["buy_method"] == "lump_sum"  # 0.20 percentile → lump_sum
    assert any(t["name"] == "weekly_drawdown" for t in rows[0]["triggers"])
