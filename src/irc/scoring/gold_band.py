from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pandas as pd


Zone = Literal["aggressive", "normal", "pause", "trim", "breakout_up", "breakout_down"]


@dataclass(frozen=True)
class BandResult:
    high: float
    low: float
    midpoint: float
    q1: float           # low + 25% of range
    q3: float           # low + 75% of range


def compute_band(prices: pd.Series, window_months: int) -> BandResult:
    """Compute 6-month rolling support/resistance band from a daily close series."""
    n = min(len(prices), window_months * 30)
    sliced = prices.tail(n)
    high = float(sliced.max())
    low = float(sliced.min())
    midpoint = (high + low) / 2
    rng = high - low
    return BandResult(
        high=high, low=low, midpoint=midpoint,
        q1=low + rng * 0.25, q3=low + rng * 0.75,
    )


def classify_zone(price: float, band: BandResult) -> Zone:
    """Map a current price to its action zone within the band."""
    if price > band.high:
        return "breakout_up"
    if price < band.low:
        return "breakout_down"
    if price <= band.q1:
        return "aggressive"
    if price <= band.midpoint:
        return "normal"
    if price <= band.q3:
        return "pause"
    return "trim"
