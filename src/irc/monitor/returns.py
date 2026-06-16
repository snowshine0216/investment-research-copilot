from __future__ import annotations

_WINDOWS = (5, 20, 60, 120, 250)


def _one(vals: list[float], w: int) -> float | None:
    if len(vals) < w + 1:
        return None
    denom = vals[-1 - w]
    if not denom:
        return None
    return round(vals[-1] / denom - 1.0, 6)


def window_returns(
    acc_nav: tuple[tuple[str, float], ...],
    windows: tuple[int, ...] = _WINDOWS,
) -> dict[int, float | None]:
    """PURE: total acc-NAV return over each trading-day window.
    return[w] = acc[-1]/acc[-1-w] - 1, rounded 6dp; None when < w+1 points
    or denominator is falsy. All windows always present as keys."""
    vals = [v for _, v in acc_nav]
    return {w: _one(vals, w) for w in windows}
