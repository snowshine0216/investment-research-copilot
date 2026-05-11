from __future__ import annotations
import pandas as pd


def coverage_check(
    triggers: dict[str, str], field_freshness_days: dict[str, int],
    max_age_days: int = 7,
) -> dict[str, bool]:
    return {
        name: (field in field_freshness_days and field_freshness_days[field] <= max_age_days)
        for name, field in triggers.items()
    }


def hit_rate_12m(history: pd.DataFrame) -> float:
    """history: per-week firing history with bool 'fired' column."""
    if history.empty:
        return 0.0
    return float(history["fired"].mean())
