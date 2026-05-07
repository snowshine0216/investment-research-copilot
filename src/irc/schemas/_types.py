from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict


AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "cash",
]
Currency = Literal["cny", "usd", "hkd"]
ScoringFactor = Literal["valuation_cost", "risk", "quality", "macro_fit", "thesis_news"]


class FrozenModel(BaseModel):
    """Base class for all immutable config models."""
    model_config = ConfigDict(frozen=True)
