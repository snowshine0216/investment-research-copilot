from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

Lookthrough = Literal["active_fund", "fund_level"] | None


@dataclass(frozen=True)
class ProfileSpec:
    lookthrough: Lookthrough
    eligible: tuple[str, ...]
    weights: dict[str, float]


# Per-profile: look-through behaviour, eligible factors, default weight vector.
# A profile NEVER allocates weight to a factor it cannot structurally fill, so a
# coverage-gate failure is always a real evidence gap (spec §3/§4/§5).
PROFILES: dict[str, ProfileSpec] = {
    "gold": ProfileSpec(
        lookthrough=None,
        eligible=("trend", "macro_tilt", "heat"),
        weights={"trend": 0.45, "macro_tilt": 0.35, "heat": 0.20},
    ),
    "qdii_global": ProfileSpec(
        lookthrough="fund_level",
        eligible=("trend", "macro_tilt", "heat", "constituent"),
        weights={"trend": 0.35, "macro_tilt": 0.35, "heat": 0.15, "constituent": 0.15},
    ),
    "active_cn_equity": ProfileSpec(
        lookthrough="active_fund",
        eligible=("trend", "valuation", "flow", "heat", "macro_tilt", "constituent"),
        weights={"trend": 0.25, "valuation": 0.20, "flow": 0.15,
                 "heat": 0.10, "macro_tilt": 0.15, "constituent": 0.15},
    ),
    "qdii_china_us_internet": ProfileSpec(
        lookthrough="fund_level",
        eligible=("trend", "valuation", "heat", "macro_tilt", "constituent"),
        weights={"trend": 0.30, "valuation": 0.20, "heat": 0.15,
                 "macro_tilt": 0.20, "constituent": 0.15},
    ),
}


def eligible_factors(profile: str) -> tuple[str, ...]:
    return PROFILES[profile].eligible


def default_weights(profile: str) -> dict[str, float]:
    return dict(PROFILES[profile].weights)


# Theme → query-seed registry. OWNED by the monitor (decoupled from research
# _DEFAULT_THEMES). Reused keys carry monitor-local seeds; new keys add coverage.
THEME_SEEDS: dict[str, str] = {
    "gold_drivers": "Recent moves in real yields, USD, central-bank gold purchases, ETF flows; cite primary sources.",
    "geopolitics": "Material geopolitical events (Russia-Ukraine, Middle East, Taiwan, chip export controls) this week with primary sources.",
    "us_monetary": "What did the Fed say or do this past week? Cite primary sources.",
    "us_fiscal_politics": "Recent US fiscal / political news affecting markets, with citations.",
    "cn_monetary": "央行最近一周的货币政策操作和表态，附原始出处。",
    "cn_equity_property_policy": "中国股市/地产监管和政策最新进展，附原始出处。",
    "global_growth": "Recent global growth / PMI / earnings-cycle signals across major economies, with primary sources.",
    "fx_cny": "近期人民币兑美元汇率走势、央行中间价与跨境资金流向，附原始出处。",
}


def theme_query_seed(theme: str) -> str:
    return THEME_SEEDS.get(theme, f"Research summary for {theme}")
