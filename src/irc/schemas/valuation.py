from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from ._types import FrozenModel


BuyMethod = Literal[
    "lump_sum", "dca_weekly", "dca_monthly", "dca_weekly_slow",
    "dca_monthly_threshold", "scaled_in_2", "scaled_in_3", "scaled_in_4",
    "threshold_triggered", "gold_anchor_plus_band", "small_account_anchor",
    "suspend",
]


class Bucket(FrozenModel):
    max_percentile: float = Field(ge=0, le=1)
    buy_method: BuyMethod
    granularity: str


class ValuationBucketsConfig(FrozenModel):
    buckets: list[Bucket] = Field(min_length=1)

    @model_validator(mode="after")
    def _ascending(self) -> "ValuationBucketsConfig":
        cuts = [b.max_percentile for b in self.buckets]
        if any(a >= b for a, b in zip(cuts, cuts[1:])):
            raise ValueError(f"buckets must be ascending by max_percentile, got {cuts}")
        if abs(cuts[-1] - 1.0) > 1e-9:
            raise ValueError(
                f"last bucket max_percentile must be 1.0 to cover all instruments, "
                f"got {cuts[-1]}"
            )
        return self
