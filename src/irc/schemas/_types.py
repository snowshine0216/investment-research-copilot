from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict


AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "cash",
]
Currency = Literal["cny", "usd", "hkd"]
ScoringFactor = Literal["valuation_cost", "risk", "quality", "macro_fit", "thesis_news"]

# Optional thematic / sector tag — drives role bucketing for sector-tilted
# instruments (passive ETFs and active funds alike). `broad` = whole-market
# core; `dividend` = factor tilt; sector tags label the industry exposure.
# Instruments with theme=None are treated as un-themed (e.g. bonds, gold).
Theme = Literal[
    "broad",
    "dividend",
    "tech", "semiconductor", "defense", "healthcare",
    "new_energy", "consumer", "finance",
    "metals", "real_estate", "soe",
]


class FrozenModel(BaseModel):
    """Base class for all immutable config models."""
    model_config = ConfigDict(frozen=True)
