from __future__ import annotations
from pydantic import Field
from ._types import FrozenModel


class OverrideEntry(FrozenModel):
    instrument_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class OverridesConfig(FrozenModel):
    boost_list: list[OverrideEntry] = Field(default_factory=list)
    ban_list: list[OverrideEntry] = Field(default_factory=list)


class OverridesFile(FrozenModel):
    include: list[OverrideEntry] = Field(default_factory=list)
    exclude: list[OverrideEntry] = Field(default_factory=list)
