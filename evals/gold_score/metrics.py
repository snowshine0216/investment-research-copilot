"""Gold-score metric functions.

The historical metrics (``drivers_freshness``, ``regime_flip_4w``,
``tilt_within_preferences_band``) read fields that the current producer
(``src/irc/commands/gold_cmd.py``) does not write. The runner no longer
calls them — they are kept here so existing tests still exercise their
logic, and they are candidates for a Phase-2 redesign that decides what
the gold-score eval should measure against today's artifact set.
"""
from __future__ import annotations
from datetime import date


_VALID_TILTS: frozenset[str] = frozenset({
    "overweight", "neutral_plus", "neutral", "neutral_minus", "underweight",
})

_EXPECTED_REGIME_FIELDS: tuple[str, ...] = (
    "regime", "vol_ratio", "adx", "trend_sign", "score",
    "tilt", "zone", "scenario", "scenario_triggers",
)


def gold_regime_schema_completeness(regime: dict) -> float:
    """Fraction of the producer's expected fields present in `regime`."""
    if not _EXPECTED_REGIME_FIELDS:
        return 1.0
    present = sum(1 for f in _EXPECTED_REGIME_FIELDS if f in regime)
    return present / len(_EXPECTED_REGIME_FIELDS)


def gold_tilt_valid_enum(tilt: object) -> float:
    return 1.0 if isinstance(tilt, str) and tilt in _VALID_TILTS else 0.0


def gold_score_in_range(score: object) -> float:
    return 1.0 if isinstance(score, (int, float)) and 0.0 <= float(score) <= 100.0 else 0.0


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
