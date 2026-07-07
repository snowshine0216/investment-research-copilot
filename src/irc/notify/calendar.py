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


def previous_trading_day(today: date, holidays: frozenset[date] | set[date]) -> date:
    """The most recent trading day strictly before `today` (skip weekends + holidays)."""
    probe = today - timedelta(days=1)
    while probe.weekday() >= _SATURDAY or probe in holidays:
        probe -= timedelta(days=1)
    return probe


def trading_day_age(
    row_date: date, today: date, holidays: frozenset[date] | set[date]
) -> int:
    """Count of trading days in the half-open interval (row_date, today].

    A row dated `today` has age 0; a row dated the previous trading day has age 1.
    Rows dated on/after `today` return 0.
    """
    if row_date >= today:
        return 0
    age = 0
    probe = today
    while probe > row_date:
        if probe.weekday() < _SATURDAY and probe not in holidays:
            age += 1
        probe -= timedelta(days=1)
    return age
