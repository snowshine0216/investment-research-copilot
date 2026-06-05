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


class ActiveFundLookthroughConfig(FrozenModel):
    """Phase D active-fund holdings look-through valuation (spec §6.2).

    Default OFF (shadow mode). PR2 flips `enabled` to true after the gate-#5
    human floor decision. `coverage_floor` is a ratio of NAV (the covered
    A-share weight must meet this). `pb_uses_pe_gate` keeps PB on the bare <30
    floor unless flipped (§3.3)."""
    enabled: bool = False
    coverage_floor: float = Field(default=0.50, gt=0.0, le=1.0)
    pb_uses_pe_gate: bool = False


class SectorIndexGroundingConfig(FrozenModel):
    """Phase B sector-index PE grounding allowlist (B1).

    `activated_slugs` is the reviewed set of sector slugs (from
    opportunity/sector_indices.py) permitted to ground a fund's valuation off
    the csindex PE percentile. B1 default = empty (accumulate only; output
    byte-identical). B2 adds reviewed mature slugs after gate #5."""
    activated_slugs: list[str] = Field(default_factory=list)


class ValuationBucketsConfig(FrozenModel):
    buckets: list[Bucket] = Field(min_length=1)
    active_fund_lookthrough: ActiveFundLookthroughConfig = Field(
        default_factory=ActiveFundLookthroughConfig
    )
    sector_index_grounding: SectorIndexGroundingConfig = Field(
        default_factory=SectorIndexGroundingConfig
    )

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
