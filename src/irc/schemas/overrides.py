from __future__ import annotations
from pydantic import BaseModel, Field


class OverrideEntry(BaseModel):
    instrument_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class OverridesConfig(BaseModel):
    boost_list: list[OverrideEntry] = Field(default_factory=list)
    ban_list: list[OverrideEntry] = Field(default_factory=list)
