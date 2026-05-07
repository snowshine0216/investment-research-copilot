from __future__ import annotations
from typing import Literal
from pydantic import Field
from ._types import FrozenModel


Comparator = Literal["<", "<=", ">", ">=", "==", "!="]


class TriggerSpec(FrozenModel):
    data_field: str = Field(min_length=1)
    comparator: Comparator
    threshold: float


class TriggersConfig(FrozenModel):
    triggers: dict[str, TriggerSpec] = Field(default_factory=dict)
