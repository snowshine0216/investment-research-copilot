from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import math
import numpy as np
import pandas as pd


Regime = Literal["range_bound", "uptrend", "downtrend"]


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    vol_ratio: float       # recent vol / baseline vol
    adx: float
    trend_sign: int        # +1 / -1 / 0


def _vol_ratio(prices: pd.Series, window_recent: int, window_baseline: int) -> float:
    rec = prices.tail(window_recent).pct_change().std()
    base = prices.tail(window_baseline).pct_change().std()
    if base == 0 or pd.isna(base):
        return 1.0
    return float(rec / base)


def _adx(prices: pd.Series, period: int = 14) -> float:
    """Plain-pandas ADX approximation. Uses close-to-close diffs as proxy for true range.

    Note: Ignoring intraday wicks means ADX values are typically 20-40% below Wilder ADX,
    biasing classification toward range_bound (downward bias — undercounts trending markets).
    Full OHLC ADX is a Plan-4 improvement once price history includes H/L columns.
    """
    df = pd.DataFrame({"close": prices})
    df["up"] = (df["close"].diff()).clip(lower=0)
    df["down"] = (-df["close"].diff()).clip(lower=0)
    df["tr"] = df["close"].diff().abs()
    df["plus_dm"] = df["up"].where(df["up"] > df["down"], 0.0)
    df["minus_dm"] = df["down"].where(df["down"] > df["up"], 0.0)
    atr = df["tr"].rolling(period).mean()
    plus_di = 100 * df["plus_dm"].rolling(period).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * df["minus_dm"].rolling(period).mean() / atr.replace(0, 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    v = dx.rolling(period).mean().iloc[-1]
    return float(v) if math.isfinite(v) else 0.0


def _trend_sign(prices: pd.Series, lookback: int = 60) -> int:
    if len(prices) < lookback:
        return 0
    delta = prices.iloc[-1] - prices.iloc[-lookback]
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0


def classify_regime(
    prices: pd.Series,
    vol_ratio_threshold: float,
    adx_threshold: float,
    window_recent_days: int = 30 * 6,
    window_baseline_days: int = 30 * 12,
) -> RegimeResult:
    """Range-bound iff vol_ratio < threshold AND ADX < threshold. Else trend by sign."""
    vol = _vol_ratio(prices, window_recent_days, window_baseline_days)
    adx = _adx(prices)
    sign = _trend_sign(prices)
    if vol < vol_ratio_threshold and adx < adx_threshold:
        regime: Regime = "range_bound"
    elif sign > 0:
        regime = "uptrend"
    else:
        regime = "downtrend"
    return RegimeResult(regime=regime, vol_ratio=vol, adx=adx, trend_sign=sign)
