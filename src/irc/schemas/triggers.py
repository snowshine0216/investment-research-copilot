from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


Comparator = Literal["<", "<=", ">", ">=", "==", "!="]


class TriggerSpec(BaseModel):
    data_field: str = Field(min_length=1)
    comparator: Comparator
    threshold: float


class TriggersConfig(BaseModel):
    triggers: dict[str, TriggerSpec] = Field(default_factory=dict)
