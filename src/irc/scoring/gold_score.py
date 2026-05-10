from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from irc.schemas.gold import GoldDriversConfig


GoldTilt = Literal["overweight", "neutral_plus", "neutral", "neutral_minus", "underweight"]


class ConfigKeyMismatch(KeyError):
    """Raised when a required gold driver key is missing from the config."""


_KNOWN_DRIVERS = (
    "real_yield_10y_tips",
    "dxy",
    "inflation_5y5y",
    "cb_purchases_wgc",
    "etf_holdings_gld",
    "geopolitical_proxy",
)


@dataclass(frozen=True)
class GoldDriverInputs:
    real_yield_10y_tips: float    # in %
    dxy: float                     # index level
    inflation_5y5y: float          # in %
    cb_purchases_yearly_tons: float
    etf_holdings_30d_change_tons: float
    geopolitical_stress_0to1: float


def _real_yield_score(v: float) -> float:
    """Lower → higher gold score. 0% → 90, 1.5% → 60, 3% → 20."""
    if v <= 0:    return 100.0
    if v <= 1.5:  return 100 - (v / 1.5) * 40
    if v <= 3.0:  return 60 - ((v - 1.5) / 1.5) * 40
    return max(0.0, 20 - (v - 3.0) * 10)


def _dxy_score(v: float) -> float:
    if v <= 95:   return 100.0
    if v <= 105:  return 100 - (v - 95) * 5
    if v <= 115:  return max(0.0, 50 - (v - 105) * 5)
    return 0.0


def _inflation_score(v: float) -> float:
    if v <= 1.5:  return 30.0
    if v <= 3.0:  return 30 + (v - 1.5) / 1.5 * 60
    return min(100.0, 90 + (v - 3.0) * 5)


def _cb_score(tons: float) -> float:
    if tons >= 1000: return 100.0
    if tons >= 500:  return 50 + (tons - 500) / 500 * 50
    return max(0.0, tons / 500 * 50)


def _etf_change_score(delta_tons: float) -> float:
    """Pulse driver. Recent inflows boost; outflows drag."""
    if delta_tons >= 30:  return 100.0
    if delta_tons >= 0:   return 50 + delta_tons / 30 * 50
    if delta_tons >= -30: return 50 + delta_tons / 30 * 50  # negative
    return 0.0


def _geo_score(stress: float) -> float:
    return max(0.0, min(100.0, stress * 100))


def compute_gold_score(inputs: GoldDriverInputs, cfg: GoldDriversConfig) -> float:
    """Weighted composite of 6 driver sub-scores → 0-100."""
    drivers = cfg.drivers if cfg.drivers is not None else {}
    for d in _KNOWN_DRIVERS:
        if d not in drivers:
            raise ConfigKeyMismatch(f"driver '{d}' missing from gold config")
    components = {
        "real_yield_10y_tips": _real_yield_score(inputs.real_yield_10y_tips),
        "dxy":                 _dxy_score(inputs.dxy),
        "inflation_5y5y":      _inflation_score(inputs.inflation_5y5y),
        "cb_purchases_wgc":    _cb_score(inputs.cb_purchases_yearly_tons),
        "etf_holdings_gld":    _etf_change_score(inputs.etf_holdings_30d_change_tons),
        "geopolitical_proxy":  _geo_score(inputs.geopolitical_stress_0to1),
    }
    total = sum(cfg.drivers[name].weight * components[name] for name in components)
    return max(0.0, min(100.0, total))


def gold_tilt_from_score(score: float) -> GoldTilt:
    if score >= 75: return "overweight"
    if score >= 55: return "neutral_plus"
    if score >= 45: return "neutral"
    if score >= 25: return "neutral_minus"
    return "underweight"
