"""PURE trading-day skip predicate. The clock + YAML read are the edge
(notify_cmd / the wrapper); this function takes the date and holiday set as
arguments. ADR 0016 §6.
"""
from __future__ import annotations

from datetime import date, timedelta

_SATURDAY = 5  # date.weekday(): Mon=0 … Sun=6


def should_skip_daily(today: date, holidays: frozenset[date] | set[date]) -> bool:
    """True on Saturday/Sunday or when `today` is a supplied holiday."""
    return today.weekday() >= _SATURDAY or today in holidays


def recent_trading_days(
    today: date, holidays: frozenset[date] | set[date], n: int
) -> tuple[date, ...]:
    """The n most recent trading days ≤ today, ascending (today last).

    Walks back day by day, skipping Sat/Sun and holidays. n must be ≥ 1.
    """
    out: list[date] = []
    cursor = today
    while len(out) < n:
        if cursor.weekday() < _SATURDAY and cursor not in holidays:
            out.append(cursor)
        cursor = cursor - timedelta(days=1)
    return tuple(reversed(out))
