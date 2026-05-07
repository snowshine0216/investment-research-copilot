from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


AssetClass = Literal[
    "gold", "cn_equity_fund", "cn_bond_fund", "cn_etf",
    "hk_etf", "us_etf", "cash"
]
GoldForm = Literal["paper_gold", "physical", "etf", "theme_fund"]
Currency = Literal["cny", "usd", "hkd"]
Broker = Literal["cmb", "huatai", "tiger", "futu", "ibkr", "schwab", "other"]
Venue = Literal[
    "cmb_fund", "cmb_gold",
    "cn_brokerage", "hk_brokerage", "us_brokerage",
]
Horizon = Literal["long_core_medium_rotation", "long_only", "rotation_focus"]
ReportLang = Literal["zh", "en"]


class Holding(BaseModel):
    asset_class: AssetClass
    form: GoldForm | None = None
    instrument_id: str | None = None
    cost_basis_cny: float = Field(ge=0)
    units: float | None = None
    hold_since: str | None = None


class Account(BaseModel):
    broker: Broker
    currency: Currency
    available_venues: list[Venue]
    holdings: list[Holding] = Field(min_length=1)


class AccountFile(BaseModel):
    accounts: list[Account] = Field(min_length=1)


class RiskBand(BaseModel):
    max_drawdown: list[float] = Field(min_length=2, max_length=2)
    horizon: Horizon

    @field_validator("max_drawdown")
    @classmethod
    def _check_band(cls, v: list[float]) -> list[float]:
        lo, hi = v
        if not (0.0 < lo < hi < 1.0):
            raise ValueError(f"max_drawdown must be 0<lo<hi<1, got {v}")
        return v


class UniverseFlags(BaseModel):
    cn_funds: bool
    cn_etfs: bool
    hk_etfs: bool
    us_etfs: bool


class AssetClassTarget(BaseModel):
    center: float = Field(ge=0, le=1)
    band: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _band_contains_center(self) -> "AssetClassTarget":
        lo, hi = self.band
        if not (0 <= lo <= self.center <= hi <= 1):
            raise ValueError(
                f"band must satisfy 0<=lo<=center<=hi<=1, got center={self.center}, band={self.band}"
            )
        return self


class CurrencyTolerance(BaseModel):
    cny: list[float] = Field(min_length=2, max_length=2)
    usd: list[float] = Field(min_length=2, max_length=2)
    hkd: list[float] = Field(min_length=2, max_length=2)

    @field_validator("cny", "usd", "hkd")
    @classmethod
    def _check_pair(cls, v: list[float]) -> list[float]:
        lo, hi = v
        if not (0.0 <= lo < hi <= 1.0):
            raise ValueError(f"tolerance must be 0<=lo<hi<=1, got {v}")
        return v


class Constraints(BaseModel):
    allow_short: bool
    allow_leverage: bool
    exclude_themes: list[str]


class InvestmentPlan(BaseModel):
    monthly_new_capital_cny: float = Field(ge=0)
    current_total_cny: float | None = Field(default=None, ge=0)


class PreferencesFile(BaseModel):
    risk_band: RiskBand
    universe: UniverseFlags
    asset_class_targets: dict[AssetClass, AssetClassTarget]
    currency_tolerance: CurrencyTolerance
    constraints: Constraints
    investment_plan: InvestmentPlan
    report_language: ReportLang

    @model_validator(mode="after")
    def _centers_sum_to_one(self) -> "PreferencesFile":
        total = sum(t.center for t in self.asset_class_targets.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(f"asset_class_targets centers must sum to ~1.0, got {total:.4f}")
        return self
