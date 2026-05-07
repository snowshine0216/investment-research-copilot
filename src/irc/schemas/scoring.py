from __future__ import annotations
import typing
from typing import Literal
from pydantic import Field, model_validator
from ._types import FrozenModel, ScoringFactor


ActionName = Literal["strong_buy_candidate", "buy_candidate", "watch", "avoid"]

_FACTOR_NAMES: frozenset[str] = frozenset(typing.get_args(ScoringFactor))


class ScoringConfig(FrozenModel):
    factor_weights: dict[ScoringFactor, float]
    action_thresholds: dict[ActionName, int]
    conviction_data_completeness_threshold: float = Field(ge=0, le=1)
    weights_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> "ScoringConfig":
        if len(self.factor_weights) != len(_FACTOR_NAMES):
            raise ValueError(f"factor_weights must include all factors: {_FACTOR_NAMES}")
        total = sum(self.factor_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"factor_weights must sum to 1.0, got {total:.6f}")
        order: tuple[ActionName, ...] = ("strong_buy_candidate", "buy_candidate", "watch", "avoid")
        missing_keys = [k for k in order if k not in self.action_thresholds]
        if missing_keys:
            raise ValueError(f"action_thresholds missing required keys: {missing_keys}")
        vals = [self.action_thresholds[k] for k in order]
        if any(a <= b for a, b in zip(vals, vals[1:])):
            raise ValueError(f"action_thresholds must be strictly descending, got {vals}")
        return self
