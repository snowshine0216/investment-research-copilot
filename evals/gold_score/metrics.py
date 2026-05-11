from __future__ import annotations
from datetime import date


def drivers_freshness(drivers: list[dict], reference_date: date | None = None) -> dict[str, int]:
    """Days since each driver was last updated. Keys are driver names."""
    ref = reference_date or date.today()
    result: dict[str, int] = {}
    for d in drivers:
        name = d.get("name", "unknown")
        updated_str = d.get("updated_at", "")
        try:
            updated = date.fromisoformat(updated_str[:10])
            result[name] = (ref - updated).days
        except (ValueError, TypeError):
            result[name] = 9999
    return result


def regime_flip_4w(regime_history: list[dict]) -> int:
    """Count regime changes in the last 4 weeks."""
    if len(regime_history) < 2:
        return 0
    flips = sum(
        1 for i in range(1, len(regime_history))
        if regime_history[i].get("regime") != regime_history[i - 1].get("regime")
    )
    return flips


def tilt_within_preferences_band(
    tilt: dict[str, float],
    preferences: dict[str, tuple[float, float]],
) -> float:
    """Fraction of tilt dimensions within user preference bounds."""
    if not preferences:
        return 1.0
    in_band = sum(
        1 for k, (lo, hi) in preferences.items()
        if lo <= tilt.get(k, 0.0) <= hi
    )
    return in_band / len(preferences)
