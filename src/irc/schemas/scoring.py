from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


FactorName = Literal["valuation_cost", "risk", "quality", "macro_fit", "thesis_news"]
ActionName = Literal["strong_buy_candidate", "buy_candidate", "watch", "avoid"]


class ScoringConfig(BaseModel):
    factor_weights: dict[FactorName, float]
    action_thresholds: dict[ActionName, int]
    conviction_data_completeness_threshold: float = Field(ge=0, le=1)
    weights_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "ScoringConfig":
        if len(self.factor_weights) != 5:
            raise ValueError("factor_weights must include all 5 factors")
        total = sum(self.factor_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"factor_weights must sum to 1.0, got {total:.6f}")
        order: tuple[ActionName, ...] = ("strong_buy_candidate", "buy_candidate", "watch", "avoid")
        vals = [self.action_thresholds[k] for k in order]
        if any(a <= b for a, b in zip(vals, vals[1:])):
            raise ValueError(f"action_thresholds must be strictly descending, got {vals}")
        return self
