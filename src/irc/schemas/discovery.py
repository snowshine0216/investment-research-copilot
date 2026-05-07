from __future__ import annotations
from pydantic import BaseModel, Field


class HardFilters(BaseModel):
    inception_years_min: int = Field(ge=0)
    cn_fund_aum_cny_min: float = Field(ge=0)
    us_etf_aum_usd_min: float = Field(ge=0)
    cn_active_expense_ratio_max: float = Field(ge=0, le=1)
    cn_passive_expense_ratio_max: float = Field(ge=0, le=1)
    us_etf_expense_ratio_max: float = Field(ge=0, le=1)
    etf_daily_volume_cny_min: float = Field(ge=0)


class QualityFilters(BaseModel):
    drawdown_3y_buffer: float = Field(gt=0)
    tracking_error_max: float = Field(ge=0, le=1)
    manager_tenure_years_min: float = Field(ge=0)


class RoleBucketConfig(BaseModel):
    min_candidates_per_role: int = Field(gt=0)
    fail_below: int = Field(ge=0)


class DiscoveryConfig(BaseModel):
    hard_filters: HardFilters
    quality_filters: QualityFilters
    role_bucket: RoleBucketConfig
