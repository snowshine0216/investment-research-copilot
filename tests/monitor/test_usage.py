from irc.schemas.monitor import MonitorConfig
from irc.monitor.usage import monitor_usage_overrides


def _cfg(n_funds: int, themes_per: int, constituent: bool) -> MonitorConfig:
    funds = [
        {
            "id": f"{i:06d}",
            "name_cn": "x",
            "market": "cn_off_exchange",
            "analysis_profile": "active_cn_equity",
            "themes": [f"t{j}" for j in range(themes_per)] or ["cn_monetary", "geopolitics"],
            "constituent_news": constituent,
            "signal_weights": {"trend": 0.40, "valuation": 0.10},
        }
        for i in range(n_funds)
    ]
    return MonitorConfig.model_validate(
        {
            "schema_version": 1,
            "defaults": {"signal_bands": {"buy": 0.4, "sell": -0.4}},
            "funds": funds,
        }
    )


def test_impact_calls_scale_with_funds_and_themes():
    # impact = per-fund (themes + holding-queries) calls, × schema-retry budget headroom
    small = monitor_usage_overrides(_cfg(2, 2, False))
    big = monitor_usage_overrides(_cfg(7, 3, True))
    assert big["monitor_impact"] > small["monitor_impact"]


def test_narrative_calls_one_per_fund():
    out = monitor_usage_overrides(_cfg(7, 2, False))
    # one narrative call per fund (× retry headroom factor handled in estimator seeds)
    assert out["monitor_narrative"] >= 7
