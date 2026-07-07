from __future__ import annotations

from datetime import date

from irc.notify.calendar import previous_trading_day, should_skip_daily, trading_day_age


def test_weekday_not_in_holidays_does_not_skip():
    # 2026-06-10 is a Wednesday.
    assert should_skip_daily(date(2026, 6, 10), set()) is False


def test_saturday_skips():
    # 2026-06-13 is a Saturday.
    assert should_skip_daily(date(2026, 6, 13), set()) is True


def test_sunday_skips():
    # 2026-06-14 is a Sunday.
    assert should_skip_daily(date(2026, 6, 14), set()) is True


def test_weekday_in_holidays_skips():
    holiday = date(2026, 10, 1)  # Thursday — CN National Day
    assert should_skip_daily(holiday, {holiday}) is True


def test_empty_holidays_only_skips_weekends():
    assert should_skip_daily(date(2026, 10, 1), set()) is False


def test_previous_trading_day_skips_weekend():
    # 2026-07-07 is a Tuesday; previous trading day is Monday 07-06.
    assert previous_trading_day(date(2026, 7, 7), frozenset()) == date(2026, 7, 6)


def test_previous_trading_day_skips_saturday_sunday_back_to_friday():
    # 2026-07-06 is a Monday; previous trading day skips Sun 07-05 + Sat 07-04 → Fri 07-03.
    assert previous_trading_day(date(2026, 7, 6), frozenset()) == date(2026, 7, 3)


def test_previous_trading_day_skips_holiday():
    holidays = {date(2026, 7, 6)}
    assert previous_trading_day(date(2026, 7, 7), holidays) == date(2026, 7, 3)


def test_trading_day_age_same_day_is_zero():
    assert trading_day_age(date(2026, 7, 7), date(2026, 7, 7), frozenset()) == 0


def test_trading_day_age_prev_trading_day_is_one():
    assert trading_day_age(date(2026, 7, 6), date(2026, 7, 7), frozenset()) == 1


def test_trading_day_age_counts_only_trading_days():
    # 2026-06-26 → 2026-07-07 spans 29,30,01,02,03,06,07 trading days = 7.
    assert trading_day_age(date(2026, 6, 26), date(2026, 7, 7), frozenset()) == 7


def test_trading_day_age_run_level_lag_example():
    # newest 07-02 as of 07-07 → 03,06,07 = 3 td (spec run-level example).
    assert trading_day_age(date(2026, 7, 2), date(2026, 7, 7), frozenset()) == 3
