import pytest
from irc.schemas.monitor import MonitorConfig
from irc.monitor.resolve import resolve_funds

_CFG = MonitorConfig.model_validate({
    "schema_version": 1,
    "defaults": {"signal_bands": {"buy": 0.40, "sell": -0.40}, "minimum_confidence": 0.50},
    "funds": [
        {"id": "008986", "name_cn": "金", "market": "cn_off_exchange",
         "analysis_profile": "gold", "themes": ["gold_drivers", "geopolitics"],
         "constituent_news": False},
        {"id": "519069", "name_cn": "价值", "market": "cn_off_exchange",
         "analysis_profile": "active_cn_equity", "themes": ["cn_monetary", "cn_equity_property_policy"],
         "constituent_news": True, "signal_weights": {"trend": 0.40, "valuation": 0.10}},
    ],
})


def test_gold_gets_profile_default_vector():
    funds = resolve_funds(_CFG)
    gold = funds[0]
    assert gold.weights == {"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20}
    assert gold.bands == {"buy": 0.40, "sell": -0.40}
    assert gold.minimum_confidence == 0.50


def test_override_composes_and_still_sums_to_one():
    funds = resolve_funds(_CFG)
    eq = funds[1]
    assert eq.weights["trend"] == 0.40 and eq.weights["valuation"] == 0.10
    assert abs(sum(eq.weights.values()) - 1.0) <= 1e-6


def test_override_breaking_sum_raises():
    bad = MonitorConfig.model_validate({
        "schema_version": 1,
        "defaults": {"signal_bands": {"buy": 0.4, "sell": -0.4}},
        "funds": [{"id": "519069", "name_cn": "x", "market": "cn_off_exchange",
                   "analysis_profile": "active_cn_equity", "themes": ["cn_monetary", "geopolitics"],
                   "constituent_news": True, "signal_weights": {"trend": 0.99}}],
    })
    with pytest.raises(ValueError, match="sum"):
        resolve_funds(bad)
