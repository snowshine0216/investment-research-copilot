from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


DriverName = Literal[
    "real_yield_10y_tips", "dxy", "inflation_5y5y",
    "cb_purchases_wgc", "etf_holdings_gld", "geopolitical_proxy",
]
DriverDirection = Literal[
    "inverse", "positive", "positive_slow", "confirmation_short", "positive_pulse",
]


class DriverSpec(BaseModel):
    weight: float = Field(ge=0, le=1)
    direction: DriverDirection


class RegimeDetection(BaseModel):
    vol_window_months: int = Field(gt=0)
    vol_baseline_window_months: int = Field(gt=0)
    vol_ratio_range_threshold: float = Field(gt=0)
    adx_range_threshold: float = Field(gt=0)


class BandConfig(BaseModel):
    rolling_window_months: int = Field(gt=0)


class GoldDriversConfig(BaseModel):
    drivers: dict[DriverName, DriverSpec]
    regime_detection: RegimeDetection
    band: BandConfig

    @model_validator(mode="after")
    def _validate(self) -> "GoldDriversConfig":
        if len(self.drivers) != 6:
            raise ValueError(f"all 6 drivers required, got {len(self.drivers)}")
        total = sum(d.weight for d in self.drivers.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"driver weights must sum to 1.0, got {total:.6f}")
        return self
