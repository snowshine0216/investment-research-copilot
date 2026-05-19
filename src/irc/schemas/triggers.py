from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._types import FrozenModel


Comparator = Literal["<", "<=", ">", ">=", "==", "!="]


class TriggerSpec(FrozenModel):
    data_field: str = Field(min_length=1)
    comparator: Comparator
    # threshold accepts numeric or string values: numeric for macro
    # series (real_yield, VIX) and instrument metrics (weekly_return);
    # string for categorical fields like valuation_state, heat_state
    # (adversarial-review item 012, 2026-05-19).
    threshold: float | str


class TriggersConfig(FrozenModel):
    triggers: dict[str, TriggerSpec] = Field(default_factory=dict)
