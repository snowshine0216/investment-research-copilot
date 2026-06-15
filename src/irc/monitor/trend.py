from __future__ import annotations
import math


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _r60(vals: list[float]) -> float:
    """Total acc-NAV return over the 60-trading-day window (or longest available).
    Returns 0.0 when the denominator is 0 or None (→ trend factor gets 0 momentum)."""
    denom = vals[-61] if len(vals) >= 61 else vals[0]
    if not denom:
        return 0.0
    return vals[-1] / denom - 1.0


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _ma_struct(vals: list[float]) -> float:
    if len(vals) < 80:                      # need MA60 today AND 20d ago
        return 0.0
    ma20 = _mean(vals[-20:])
    ma60_today = _mean(vals[-60:])
    ma60_prev = _mean(vals[-80:-20])
    slope = ma60_today - ma60_prev
    if ma20 > ma60_today and slope >= 0:
        return 1.0
    if ma20 < ma60_today and slope < 0:
        return -1.0
    return 0.0


def _drawdown_250(vals: list[float]) -> float:
    window = vals[-250:]
    peak = max(window)
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - vals[-1]) / peak)


def trend_score(acc_nav: tuple[tuple[str, float], ...]) -> float:
    """PINNED blend (spec §4): 0.50·tanh(8·r60) + 0.30·ma_struct + 0.20·(-drawdown),
    clamped to [-1, 1]. Pure; caller guarantees len ≥ minimum_observations."""
    vals = [v for _, v in acc_nav]
    momentum = math.tanh(8.0 * _r60(vals))
    structure = _ma_struct(vals)
    dd = _drawdown_250(vals)
    return _clamp(0.50 * momentum + 0.30 * structure + 0.20 * (-dd))
