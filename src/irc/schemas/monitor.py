from __future__ import annotations
from typing import Literal
from pydantic import Field, field_validator, model_validator
from ._types import FrozenModel

Market = Literal["cn_off_exchange", "cn_on_exchange"]
AnalysisProfile = Literal["gold", "qdii_global", "active_cn_equity", "qdii_china_us_internet"]
_ID_RE = r"^\d{6}$"


class MonitorFundConfig(FrozenModel):
    id: str = Field(pattern=_ID_RE)
    name_cn: str = Field(min_length=1)              # DISPLAY-ONLY; never routes
    market: Market
    analysis_profile: AnalysisProfile
    themes: tuple[str, ...] = ()
    constituent_news: bool = False
    signal_weights: dict[str, float] | None = None  # per-fund override (composed in Task 3)
    signal_bands: dict[str, float] | None = None
    minimum_confidence: float | None = None

    @field_validator("themes")
    @classmethod
    def _themes_nonempty(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not t.strip() for t in v):
            raise ValueError("theme keys must be non-empty")
        return v

    @field_validator("signal_bands")
    @classmethod
    def _check_bands(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        return _validate_bands(v) if v else v


class MonitorHistoryConfig(FrozenModel):
    minimum_observations: int = Field(default=251, ge=1)
    fetch_calendar_days: int = Field(default=550, ge=1)


class MonitorDefaults(FrozenModel):
    # Weights are NOT a config default: the sole weight-governance surface is
    # profiles.py `PROFILES[profile].weights` (overlaid by the per-fund
    # `MonitorFundConfig.signal_weights` override). resolve.py reads these
    # defaults only for `signal_bands` and `minimum_confidence`. See ADR 0018 D2.
    return_windows: tuple[int, ...] = (5, 20, 60, 120, 250)
    signal_bands: dict[str, float] = Field(default_factory=dict)
    minimum_confidence: float = Field(default=0.50, ge=0.0, le=1.0)

    @field_validator("signal_bands")
    @classmethod
    def _check_bands(cls, v: dict[str, float]) -> dict[str, float]:
        return _validate_bands(v)


class MonitorConfig(FrozenModel):
    schema_version: int = Field(ge=1)
    history: MonitorHistoryConfig = Field(default_factory=MonitorHistoryConfig)
    defaults: MonitorDefaults = Field(default_factory=MonitorDefaults)
    funds: tuple[MonitorFundConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_dup_ids(self) -> "MonitorConfig":
        seen: set[str] = set()
        for f in self.funds:
            if f.id in seen:
                raise ValueError(f"duplicate fund id in monitor config: {f.id}")
            seen.add(f.id)
        return self


def _validate_bands(bands: dict[str, float]) -> dict[str, float]:
    if not bands:
        return bands
    buy, sell = bands.get("buy"), bands.get("sell")
    if buy is None or sell is None:
        raise ValueError("signal_bands needs both 'buy' and 'sell'")
    if not (-1.0 <= sell < buy <= 1.0):
        raise ValueError(f"signal_bands require -1 <= sell < buy <= 1; got buy={buy} sell={sell}")
    return bands


_WEIGHT_SUM_TOL = 1e-6


def compose_weights(
    base: dict[str, float], override: dict[str, float] | None,
) -> dict[str, float]:
    """Overlay a per-fund override on the profile default vector (immutable)."""
    return {**base} if not override else {**base, **override}


def weights_sum_ok(weights: dict[str, float]) -> bool:
    return abs(sum(weights.values()) - 1.0) <= _WEIGHT_SUM_TOL
