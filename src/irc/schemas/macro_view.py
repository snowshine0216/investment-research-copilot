from __future__ import annotations
from pydantic import Field
from ._types import FrozenModel, ScoringFactor


class MacroViewEntry(FrozenModel):
    text: str = Field(min_length=1)
    biased_factor: ScoringFactor
    bias: float = Field(ge=-0.30, le=0.30)


class MacroViewConfig(FrozenModel):
    views: list[MacroViewEntry] = Field(default_factory=list)
    active: bool = False
