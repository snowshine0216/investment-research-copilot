"""PURE trading-day skip predicate. The clock + YAML read are the edge
(notify_cmd / the wrapper); this function takes the date and holiday set as
arguments. ADR 0016 §6.
"""
from __future__ import annotations

from datetime import date

_SATURDAY = 5  # date.weekday(): Mon=0 … Sun=6


def should_skip_daily(today: date, holidays: frozenset[date] | set[date]) -> bool:
    """True on Saturday/Sunday or when `today` is a supplied holiday."""
    return today.weekday() >= _SATURDAY or today in holidays
