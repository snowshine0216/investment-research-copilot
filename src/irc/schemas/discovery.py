from __future__ import annotations

from typing import Final

from pydantic import Field, model_validator

from ._types import FrozenModel


# AC9: named Final constant so the magic number has a name (mirrors
# FOREIGN_HEAVY_THRESHOLD in policy_b.py). YAML key stays lowercase per
# existing config convention; the constant lives at module scope so
# downstream consumers can introspect the default without instantiating.
QDII_MAX_PREMIUM_DEFAULT: Final[float] = 0.05


class HardFilters(FrozenModel):
    inception_years_min: int = Field(ge=0)
    cn_fund_aum_cny_min: float = Field(ge=0)
    us_etf_aum_usd_min: float = Field(ge=0)
    cn_active_expense_ratio_max: float = Field(ge=0, le=1)
    cn_passive_expense_ratio_max: float = Field(ge=0, le=1)
    us_etf_expense_ratio_max: float = Field(ge=0, le=1)
    qdii_feeder_expense_ratio_max: float = Field(default=0.012, ge=0, le=1)
    etf_daily_volume_cny_min: float = Field(ge=0)
    qdii_max_premium_pct: float = Field(
        default=QDII_MAX_PREMIUM_DEFAULT, ge=0, le=1
    )


class QualityFilters(FrozenModel):
    drawdown_3y_buffer: float = Field(gt=0)
    drawdown_3y_buffer_by_asset_class: dict[str, float] = Field(default_factory=dict)
    tracking_error_max: float = Field(ge=0, le=1)
    manager_tenure_years_min: float = Field(ge=0)


class RoleBucketConfig(FrozenModel):
    min_candidates_per_role: int = Field(gt=0)
    fail_below: int = Field(ge=0)

    @model_validator(mode="after")
    def _fail_below_lt_min(self) -> "RoleBucketConfig":
        if self.fail_below >= self.min_candidates_per_role:
            raise ValueError(
                f"fail_below ({self.fail_below}) must be < min_candidates_per_role ({self.min_candidates_per_role})"
            )
        return self


class DiscoveryConfig(FrozenModel):
    hard_filters: HardFilters
    quality_filters: QualityFilters
    role_bucket: RoleBucketConfig
