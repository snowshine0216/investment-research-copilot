from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


BiasFactor = Literal["macro_fit", "thesis_news", "risk", "quality", "valuation_cost"]


class MacroViewEntry(BaseModel):
    text: str = Field(min_length=1)
    biased_factor: BiasFactor
    bias: float = Field(ge=-0.30, le=0.30)


class MacroViewConfig(BaseModel):
    views: list[MacroViewEntry] = Field(default_factory=list)
    active: bool = False
