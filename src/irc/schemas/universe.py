from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from ._types import FrozenModel, AssetClass, Currency, Theme


Market = Literal[
    "cn_on_exchange", "cn_off_exchange",
    "hk_on_exchange", "us_on_exchange",
    "cmb_internal",
]


class Instrument(FrozenModel):
    instrument_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    market: Market
    name_cn: str = Field(min_length=1)
    name_en: str | None = None
    asset_class: AssetClass
    currency: Currency
    tracked_index: str | None = None
    theme: Theme | None = None
    venue_required: list[str] = Field(default_factory=list)


class UniverseConfig(FrozenModel):
    instruments: list[Instrument] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_duplicates(self) -> "UniverseConfig":
        ids = [i.instrument_id for i in self.instruments]
        if len(ids) != len(set(ids)):
            seen: set[str] = set()
            dups = [x for x in ids if x in seen or seen.add(x)]  # type: ignore
            raise ValueError(f"duplicate instrument_ids: {dups}")
        return self
